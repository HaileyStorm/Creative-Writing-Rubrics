# CWR-guided revision gain v2 live execution v2

This is the versioned successor to the committed v1 one-cell adapter. It pins
the same frozen v2 lean pilot and retains v1's route reauthentication,
one-launch/no-resend, reconciliation-only, receipt-authority, and judge
separation rules.

The two v1 postlaunch roots are immutable `terminal_no_vote_unknown_contact`
lineage. Their exact prepared/admission/payload/route/intent/terminal hashes
and the absence of receipt/control artifacts are rechecked locally. They are
neither reconciled nor resent. V2 accepts only a fresh run root and records
that exclusion in its frozen contract.

Each V2 outbound request wraps the frozen pilot payload in a versioned
successor study, event, and logical-sample identity. The source text remains
unchanged, but the actual transmitted request cannot be the V1 logical cell.

Immediately after an adapter subprocess returns, V2 persists its exact stdout
bytes before checking the exit code or parsing the envelope. It then accepts
only the installed shared adapter's standard sorted, ASCII-escaped `json.dumps`
serialization with precisely one LF or CRLF. The canonical UTF-8 control file
is a separate local projection. BOMs, extra lines, trailing bytes, compact
serialization, and other alternate encodings are rejected while the raw bytes
remain available for terminal reconciliation evidence.

On a subprocess timeout, any captured stdout and stderr bytes are each written
and bound before the postlaunch terminal record. They are never parsed into a
control envelope or accepted as a receipt.

No dispatch occurs without `allow_remote=True` and a newly revalidated exact
route. This package has no automatic retry, resend, confirmation, pooling, or
promotion path.
