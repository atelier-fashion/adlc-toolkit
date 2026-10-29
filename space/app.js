// space/app.js — the page's DOM layer (REQ-670 ADR-2). The intake rules live in intake.js;
// this file decides what a click does (sample, ask for a source, or run), wires inputs to
// intake.js, and renders what comes back.
//
// Rendering uses textContent and createElement only, so model output and pasted text are
// shown as text, never parsed as HTML (BR-6). The key is read from its input at click
// time and handed to runIntake; it is not kept anywhere else. Nothing is written to
// browser storage, and nothing is logged (BR-1, BR-8).
//
// The decisions below the DOM (what a click does, what the download holds, what the next
// step says) are exported under Node so space/tests/page.test.js covers them.

(function (g) {
  'use strict';

  // No key shows the sample and makes no call (BR-2); an empty source asks for one.
  function decideRun(apiKey, source) {
    if (!apiKey || !String(apiKey).trim()) return 'sample';
    if (!source || !String(source).trim()) return 'empty';
    return 'run';
  }

  async function handleRun(opts) {
    var decision = decideRun(opts.apiKey, opts.source);
    if (decision === 'sample') return { kind: 'sample', result: opts.sample.output };
    if (decision === 'empty') return { kind: 'empty' };
    var result = await opts.intake.runIntake({
      source: opts.source,
      apiKey: String(opts.apiKey).trim(),
      config: opts.config,
      toolkit: opts.toolkit,
      fetchImpl: opts.fetchImpl,
    });
    return result.error ? { kind: 'error', error: result.error } : { kind: 'result', result: result };
  }

  // BR-11: the download is exactly the requirement the page displays.
  function downloadText(result) {
    return result.requirement_md;
  }

  function nextStepText(toolkit) {
    return toolkit.installCommands
      .concat(['', '# then, in Claude Code, inside your repository:', '/adlc:spec --intake notes.md'])
      .join('\n');
  }

  // Generous: 1 KiB a line over the whole budget. The line budget itself is checked by
  // runIntake, which refuses without truncating.
  function maxUploadBytes(toolkit) {
    return toolkit.maxLines * 1024;
  }

  function redactionText(result) {
    var n = result.redaction_count || 0;
    if (result.synthetic) return 'Sample run on a synthetic transcript. Enter your key to run on your own notes.';
    return n === 1 ? '1 credential-shaped string was removed before sending.' : n + ' credential-shaped strings were removed before sending.';
  }

  function mount(doc, win) {
    var $ = function (id) {
      return doc.getElementById(id);
    };
    var toolkit = win.ADLC_TOOLKIT;
    var sample = win.ADLC_SAMPLE;
    var intake = win.AdlcIntake;
    var config = null;
    var current = null;

    function setStatus(text, isError) {
      $('status').textContent = text;
      $('status').className = isError ? 'error' : '';
    }

    function render(kind, result) {
      current = result;
      $('output-kind').textContent = kind === 'sample' ? '(sample)' : '(your run)';
      $('redactions').textContent = redactionText(result);
      $('requirement').textContent = result.requirement_md;
      var list = $('gaps');
      while (list.firstChild) list.removeChild(list.firstChild);
      if (!result.gaps.length) {
        var none = doc.createElement('li');
        none.textContent = 'No gaps: the source answered every section.';
        list.appendChild(none);
      }
      result.gaps.forEach(function (gap) {
        var li = doc.createElement('li');
        var sev = doc.createElement('span');
        sev.className = 'sev sev-' + gap.severity;
        sev.textContent = gap.severity;
        li.appendChild(sev);
        li.appendChild(doc.createTextNode(' [' + gap.section + '] ' + gap.question));
        var why = doc.createElement('span');
        why.className = 'why';
        why.textContent = gap.justification;
        li.appendChild(why);
        list.appendChild(li);
      });
      $('download').disabled = false;
    }

    $('toolkit-version').textContent = toolkit.version;
    $('max-lines').textContent = String(toolkit.maxLines);
    $('next-step').textContent = nextStepText(toolkit);
    render('sample', sample.output);
    $('run').disabled = true;

    // BR-9: the model comes from config.json and is on the page before any key is entered.
    win
      .fetch('config.json', { cache: 'no-store' })
      .then(function (res) {
        if (!res.ok) throw new Error('config.json ' + res.status);
        return res.json();
      })
      .then(function (c) {
        if (!c || typeof c.model !== 'string' || typeof c.max_tokens !== 'number') throw new Error('config.json is malformed');
        config = c;
        $('model-id').textContent = c.model;
        $('run').disabled = false;
      })
      .catch(function () {
        $('model-id').textContent = 'unavailable';
        setStatus('The Space configuration could not be loaded, so live runs are off. The sample still works.', true);
      });

    // Uploads become pasted text (LESSON-606). A file far past the budget is refused
    // before it is read, so a huge or binary file cannot hang the tab.
    $('file').addEventListener('change', function (ev) {
      var file = ev.target.files && ev.target.files[0];
      if (!file) return;
      if (file.size > maxUploadBytes(toolkit)) {
        setStatus(file.name + ' is too large to be a ' + toolkit.maxLines + '-line source.', true);
        ev.target.value = '';
        return;
      }
      file
        .text()
        .then(function (text) {
          $('source').value = intake.normalize(text);
          setStatus('Loaded ' + file.name + ' (' + intake.countLines($('source').value) + ' lines).');
        })
        .catch(function () {
          setStatus('Could not read ' + file.name + '.', true);
          ev.target.value = '';
        });
    });

    $('run').addEventListener('click', function () {
      if (!config) return;
      $('run').disabled = true;
      setStatus('Working…');
      handleRun({
        apiKey: $('api-key').value,
        source: $('source').value,
        config: config,
        toolkit: toolkit,
        sample: sample,
        intake: intake,
        fetchImpl: win.fetch.bind(win),
      })
        .then(function (out) {
          if (out.kind === 'sample') {
            render('sample', out.result);
            setStatus('No key entered, so this is the sample run. Nothing was sent.');
          } else if (out.kind === 'empty') {
            setStatus('Paste notes or upload a .txt or .md file first.', true);
          } else if (out.kind === 'error') {
            setStatus(out.error.message, true);
          } else {
            render('result', out.result);
            setStatus('Done. Nothing was stored.');
          }
        })
        .catch(function () {
          setStatus(intake.ERROR_LABELS.unclassified + ': the page could not complete the run.', true);
        })
        .then(function () {
          $('run').disabled = false;
        });
    });

    $('download').addEventListener('click', function () {
      if (!current) return;
      var url = win.URL.createObjectURL(new win.Blob([downloadText(current)], { type: 'text/markdown' }));
      var a = doc.createElement('a');
      a.href = url;
      a.download = 'requirement.md';
      doc.body.appendChild(a);
      a.click();
      doc.body.removeChild(a);
      // Some browsers cancel a download whose URL is revoked at once.
      win.setTimeout(function () {
        win.URL.revokeObjectURL(url);
      }, 10000);
    });
  }

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
      decideRun: decideRun,
      handleRun: handleRun,
      downloadText: downloadText,
      nextStepText: nextStepText,
      redactionText: redactionText,
      maxUploadBytes: maxUploadBytes,
      mount: mount,
    };
  } else {
    g.document.addEventListener('DOMContentLoaded', function () {
      mount(g.document, g);
    });
  }
})(this);
