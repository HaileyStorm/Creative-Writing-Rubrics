# CWR-guided revision-gain V9 historical-input replay

V9 is a provider-free, historical-development replay of the completed 40-cell
V7 endpoint root. It retains V8's independent receipt replay and the narrowly
defined LF/CRLF adapter-stdout acceptance, but fixes the current-checkout
dependency drift without changing V7 or V8.

The V7 source pins the original V6 executor SHA-256
`e0f4181e4daed637b6c8e438e71b90129505bd2191202dd2ef43e0f7e406d172`.
The current V6 successor is intentionally different, so V9 obtains the exact
historical V6 bytes only from Git commit `c24a9ec` and blob
`100c9e70ebe4d550249c47e5f775b30d4515361a`; it verifies both that immutable
Git binding and the V6 SHA-256 before injecting those bytes into V7's existing
replay path. It never substitutes the current V6 file.

Use a local checkout with that commit reachable and an explicit completed V7
root:

`python executor.py --source-root <absolute-completed-v7-root> --output result.json`

The result has 40 endpoint receipts, 16 guided-minus-control rows, and 32
arm-minus-baseline rows. Grok and Sol remain separately identified and scored;
no pooled endpoint, provider-ranking, promotion, or generalization claim is
made. Its V8 projection hash is pinned in the contract and the result explicitly
states `exact_parity` or `discrepancy`. It makes no provider, queue, or remote
call. Sol native endpoint-contact cardinality remains unproven.
