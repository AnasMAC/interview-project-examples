
# Finding Importer - Submission Document

## 1. Run Guide & Execution Evidence

**Prerequisites:** Python 3.10 or later. No external packages required.

**To run the test suite:**
```sh
python3 -m unittest discover -s tests -p '*_test.py' -v

```

*Expected Output:* `Ran 9 tests in 0.255s. OK`

**To process the primary fixture:**

```sh
python3 app.py --input inputs/primary.json --tenant north

```

*Representative Output (Summary):*
The batch processes successfully with `exit 0`, identifying 5 rejected rows and merging the remaining 5 into 3 unique findings:

```json
  "summary": {
    "accepted_rows": 5,
    "duplicate_rows": 2,
    "input_rows": 10,
    "rejected_rows": 5,
    "unique_findings": 3
  }

```

*Evidence of merging:* Source IDs `r1` and `r2` are successfully merged into a single `critical` finding for the `auth` rule at `https://api.example.test/login`.

**To test error handling (Malformed Input & Tenant Mismatch):**

```sh
python3 app.py --input inputs/malformed-input.txt 
# error: Expecting ',' delimiter: line 2 column 1 (char 34)

python3 app.py --input inputs/primary.json --tenant south
# error: Tenant in JSON does not match the CLI argument.

```

---

## 2. Decision and Work Log

* **Priorities:** I focused on keeping the architecture simple and linear, processing records in O(n) time. I prioritized a clean separation of concerns by using helper functions (a "manager/servant" pattern) for top-level validation, row-level validation, and deduplication.
* **Deferred:** I deferred using advanced third-party libraries for validation (like Pydantic) or JSON streaming, sticking strictly to the standard library constraints.
* **Obstacles & Response:** As someone who does not code in Python daily, I faced obstacles with Python-specific dictionary syntax (e.g., `.setdefault()`). I responded by writing the core algorithmic logic and flow by hand, then using AI purely to correct my syntax errors.
* **Validation & Refinement:** I validated that the application correctly isolates failures without crashing. For example, in the primary fixture, row 4 (`source_id: r4`) is gracefully rejected because `evidence` is empty, and row 6 (`source_id: r6`) is rejected because the asset ID is not in the allowed list, while the rest of the batch succeeds.
* **Known Limits & Next Steps:** The current implementation loads the entire JSON file into memory at once. If this tool needed to scale to massive production files, the next step would be implementing a chunked map-reduce approach: dividing the rows into groups, using a pool of workers to process those chunks in parallel, and applying a "merge sort" style logic to combine the final deduplicated results.

---

## 3. AI-Use Note

I wrote the logic, architecture, and validation requirements by hand. Because I am not primarily a Python developer, I used an AI assistant to help correct Python-specific syntax errors, explain standard library data structures (like dictionary manipulation and immutable tuples), and help structure the `unittest` syntax. All logic was manually integrated and verified through the terminal.

---

## 4. Feature Walkthrough

**Core Workflow:**
The script begins by loading the JSON and immediately performing top-level validation to ensure the schema is intact and the CLI tenant matches the payload tenant. It then iterates through the `records` array in O(n) time. Each row is passed to a validation helper. If it fails, the error and row number are appended to the `rejected` list. If it passes, the row is passed to the deduplication helper. Deduplication is handled efficiently by storing findings in a dictionary using an immutable tuple `(tenant, asset_id, rule_id, location)` as the key. If the key exists, the arrays for `evidence` and `source_ids` are merged and sorted, and the severity is upgraded if the new row is higher.

**Edge Case Handling:**
The deduplication logic strictly honors exact location identity and empty string rules. By stripping whitespace before validation, the script catches "hidden" empty fields (like row 8, `r8`, which had an empty `rule_id`). Furthermore, because the exact location string is part of the tuple key, a row with an `http://` scheme will correctly not merge with an `https://` row, preserving significant URL details.

**Evidence of Execution:**
As shown in the terminal traces provided above, the primary fixture successfully outputs 3 `findings` and 5 `rejected` diagnostics. The test suite includes 9 passing assertions covering top-level mismatches, empty batches, evidence merging, and severity upgrading, proving the logic behaves exactly to the requested contract.

```

```
