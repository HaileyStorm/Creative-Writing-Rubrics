# Lower-step Grok execution v3: callback prompt staging

V3 pins the committed V2 slot-visibility successor. Initial admission remains
pristine. At callback time, it permits exactly one plain runner-staged
`responses/batch-0001.attempt-0001.prompt.txt` file, only when its bytes and
SHA-256 equal the cell's admitted `prompt-request.bin` and scheduled payload
identity. Missing, altered, misnamed, reparse, or extra response artifacts are
rejected before launch intent or native contact.

The terminal V2 zero-contact root remains immutable; V3 requires a separate
fresh root and retains V2's ten-slot ceiling, no-resend, and package-lineage
gates.
