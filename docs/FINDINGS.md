# Findings and evidence

The four modules build on the original Model Armor decoding implementation.
All verdicts below are observations for particular prompts, not universal claims.
`attack_tests.md` is the user's unchanged raw transcript; `attack_solutions.md`
is the implementation brief. No new live attack probes were run during this work.

| Finding | Evidence | Backend response |
|---|---|---|
| 1. Encoding/representation | Teammate's earlier README records Base64, hex, decimal and split/nested bypasses. The original payload definitions remain in `presets.LEGACY_PRESETS`. | Bounded decoding; original and revealed content receive Guard checks and local/context inspection. Benign encodings may pass with WARN. |
| 2. Character obfuscation | Plaintext blocked (`34a9280af8e4`); spaced allowed (`1220112867b2`), hyphen allowed (`9c54743174cd`), underscore allowed (`db006d6ce8e7`), leetspeak allowed (`d0e87cbeeadd`). | Reconstruct selected instruction words, normalize Unicode and whitespace, apply word-specific leetspeak mapping, then inspect both forms. |
| 3. Context false positives | Explanation blocked (`1fc450d792b7`), classification blocked (`5e6b1040dd1d`), research-paper example blocked (`c6679ee6601a`). | Quote-scope analysis recognizes analytical intent. Injection-only disputes become REVIEW and never call the LLM. |
| 4. Session blindness | Remember verb allowed (`8b0e40cbd886`), remember phrase allowed (`88ec9703ade9`), combine instruction allowed (`46bcd912c3fb`). | Retain bounded fragments, build combined representations, detect composition, maintain decaying risk and real delivered chat history. |

## Limits on the encoding claim

The newer transcript **blocked** the tested Base64 framing (`f7408ee2e4d9`),
hex framing (`3c8ef06759c7`) and URL framing (`0a4a67f72f53`). It also blocked
zero-width, full-width, slash-separated and several structured wrappers.
These observations refine the earlier claim: behavior depends on wording and
representation. The comparator reports actual results and never fabricates an ALLOW.
The original teammate README is preserved in `MODEL_ARMOR_ORIGINAL.md` for provenance.

## What the implementation proves offline

The tests mock Guard responses, including an all-clear Guard, to verify Athena's
independent reconstruction, detection, policy and delivery boundaries. They do not
establish current Guard bypass rates or downstream LLM compliance. Tests with a
mocked injection-only block verify REVIEW without overriding the block.

## Additional defects repaired

- No head truncation: complete current messages and bounded history are inspected.
  Long inspection representations are split with overlap. Exceeding inspection
  limits blocks instead of accepting partially inspected data.
- Rejected model output is absent from responses, evidence, history and logs.
- The historical CLI leak demonstration now sends the exact encoded payload that
  was screened. The new four-finding CLI demonstrates comparisons without a raw
  unprotected model call.
- Delivered turns form real LLM conversation history. Session access is serialized.
- Guard booleans, statuses and check completeness are validated. Malformed values,
  missing checks, partial results, timeouts and quota errors block delivery.
- A person's name such as Dan is no longer a standalone injection match.
- Activity logs contain metadata only, including session hashes and latencies.
