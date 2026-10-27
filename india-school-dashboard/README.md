# India school education dashboard

## Run the dashboard and analyst chatbot

1. Install Python 3.10 or newer.
2. In PowerShell, run `Copy-Item .env.example .env`, then edit `.env` and set `GROQ_API_KEY` to your Groq API key.
3. From this folder, run `python server.py`.
4. Open `http://127.0.0.1:8000`.

Dashboard charts are drawn with local SVG rendering and do not require an external chart library or internet access. The key stays in the local `.env` file and is never sent to the browser. If no key is configured, the chatbot clearly reports that and still provides its local, dataset-based answer.

## Government vs. private comparison

The overview includes a year-by-year national comparison for every academic year from 2012–13 through 2025–26, covering schools, enrolment and teachers, with estimated pupil–teacher ratios derived from those figures. The source management extract reports government and private-unaided counts for 2023–24 and 2024–25; the 2024–25 enrolment rows are flagged as duplicated and are not used as an observed split. For years without a reliable split, the dashboard applies the 2023–24 management shares to the official annual national totals. If a national total is absent, it interpolates or extrapolates from the nearest reported totals.

Each comparison row is marked as observed or estimated. Estimates are for exploratory analysis only, are not official UDISE+ management counts, and should be verified before policy use. State-level management splits, and management-specific dropout, GER and facility statistics, are not inferred because the supplied sources do not report them.

## Included cleaned datasets

The cleaned `indian_government_schools_cleaned.zip` indicators are represented in the multi-year trend data (dropout, GER and facilities). The `Indian_privateschools_cleaned.zip` extracts are used for private unaided enrolment, West Bengal teacher qualifications and the Farrukhabad facilities snapshot. The 2019–20 district-by-age boys/girls file is also kept locally at `data/boys_and_girls_enrolement.csv`; the server aggregates it to state and class totals for the dashboard and chatbot. That source does not report school management, so its class-wise totals are not labelled as private-school-only. Private unaided enrolment totals are shown separately because their source does not state an academic year. The supplied cleaning report flags structural damage in the legacy private-enrolment and teacher-qualification workbooks, so those values should be verified against the originals before policy use.

Keep the `data` folder alongside `server.py`; the class-wise enrolment view uses the local `/api/supplemental-data` endpoint.

## 2011-12 → 2025-26 update: observed vs estimated data

The dashboard now has a value for every academic year from 2011-12 to 2025-26.

- **Published figures are untouched.** Every value from the original extracts is kept exactly as supplied.
- **Added official anchors** (listed in *Data Sources & Methodology → Data provenance*): NITI Aayog (2026) national enrolment 2014-15 → 2019-20, schools 2014-15, 2024-25 GER / dropout / electricity; PIB (28 Aug 2025) zero-enrolment schools 2022-23 → 2024-25 and girls' share of enrolment 2023-24 / 2024-25.
- **Estimates are flagged.** Cells with no published figure are filled by linear interpolation between published years, or (outside the published range) by moving the nearest published state value in line with the national trend. In the data, these rows carry a 5th element `"e"`; in the UI they show `e` or `*`.
- **Entities only exist when they existed.** Telangana (from 2013-14), Ladakh (from 2019-20), and the Dadra & Nagar Haveli / Daman & Diu merger (separate until 2016-17, merged from 2017-18) are only filled within their valid years.
- **Known limits.** National totals for 2011-12 to 2013-14 are extrapolated backwards and likely overstate enrolment. UDISE+ moved to student-wise records in 2022-23, so values before and after are not strictly comparable. Estimates are for exploration, not official statistics. Replace them with official figures by editing `D.rows` / `D.nat` and removing the `"e"` flag.
