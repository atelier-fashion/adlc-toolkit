# Fixture: opts into the delegate gate but omits the canonical literals.

The gate mentions ADLC_DISABLE_DELEGATE but the rest of the helpers are
missing. Each of the five required literals should fire as a finding.
