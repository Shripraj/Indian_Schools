import csv
import json
import math
import os
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent
HTML_FILE = ROOT / "india-school-education-dashboard (1).html"
GENDER_ENROLMENT_FILE = ROOT / "data" / "boys_and_girls_enrolement.csv"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "llama-3.3-70b-versatile"
MAX_REQUEST_BYTES = 30000


def load_env_file():
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        os.environ.setdefault(name.strip(), value.strip().strip("\"'"))


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        if data.strip():
            self.parts.append(data.strip())


def evidence_as_text(value):
    parser = PlainText()
    parser.feed(value)
    return " ".join(parser.parts)[:18000]


def load_gender_enrolment():
    totals = {}
    class_columns = [
        (str(class_number), f"class_{class_number}_{gender}")
        for class_number in range(1, 13)
        for gender in ("boys", "girls")
    ]
    required = {"ac_year", "state_name", *(column for _, column in class_columns)}

    with GENDER_ENROLMENT_FILE.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        missing = required.difference(reader.fieldnames or ())
        if missing:
            raise ValueError("Missing required enrolment columns: " + ", ".join(sorted(missing)))

        for row_number, record in enumerate(reader, start=2):
            year = (record.get("ac_year") or "").strip()
            state = (record.get("state_name") or "").strip()
            if not year or not state:
                raise ValueError(f"Missing year or state on source row {row_number}")
            if state.casefold() in {"india", "all india"}:
                continue

            state_totals = totals.setdefault(year, {}).setdefault(
                state,
                {
                    class_number: {
                        "boys": {"value": 0.0, "complete": True},
                        "girls": {"value": 0.0, "complete": True},
                    }
                    for class_number in range(1, 13)
                },
            )
            for class_number, column in class_columns:
                raw = (record.get(column) or "").strip()
                gender = column.rsplit("_", 1)[1]
                cell = state_totals[int(class_number)][gender]
                if not raw:
                    cell["complete"] = False
                    continue
                try:
                    value = float(raw)
                except ValueError as exc:
                    raise ValueError(f"Invalid enrolment on source row {row_number}") from exc
                if not math.isfinite(value) or value < 0:
                    raise ValueError(f"Invalid enrolment on source row {row_number}")
                cell["value"] += value

    def count_value(cell):
        value = cell["value"] if cell["complete"] else None
        return int(value) if value is not None and value.is_integer() else value

    rows = []
    for year, states in sorted(totals.items()):
        national = {
            class_number: {
                gender: {"value": 0.0, "complete": True}
                for gender in ("boys", "girls")
            }
            for class_number in range(1, 13)
        }
        for state, class_totals in sorted(states.items()):
            classes = {}
            for class_number, gender_totals in class_totals.items():
                boys = count_value(gender_totals["boys"])
                girls = count_value(gender_totals["girls"])
                classes[str(class_number)] = {
                    "boys": boys,
                    "girls": girls,
                    "total": boys + girls if boys is not None and girls is not None else None,
                }
                for gender, count in (("boys", boys), ("girls", girls)):
                    cell = national[class_number][gender]
                    if count is None:
                        cell["complete"] = False
                    else:
                        cell["value"] += count
            rows.append({"year": year, "state": state, "classes": classes})

        national_classes = {}
        for class_number, gender_totals in national.items():
            boys = count_value(gender_totals["boys"])
            girls = count_value(gender_totals["girls"])
            national_classes[str(class_number)] = {
                "boys": boys,
                "girls": girls,
                "total": boys + girls if boys is not None and girls is not None else None,
            }
        rows.append({"year": year, "state": "All India", "classes": national_classes})

    if not rows:
        raise ValueError("The enrolment dataset contains no usable state records")
    return {"rows": rows}


class DashboardHandler(BaseHTTPRequestHandler):
    server_version = "SchoolDashboard/1.0"

    def send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            self.send_json(200, {"status": "ok", "groq_configured": bool(os.getenv("GROQ_API_KEY"))})
            return
        if self.path == "/api/supplemental-data":
            try:
                self.send_json(200, load_gender_enrolment())
            except (OSError, csv.Error, ValueError) as exc:
                self.log_error("Could not load supplemental enrolment data: %s", exc)
                self.send_json(500, {"error": "The class-by-gender enrolment dataset could not be loaded."})
            return
        if self.path not in ("/", "/index.html"):
            self.send_error(404)
            return
        try:
            body = HTML_FILE.read_bytes()
        except OSError as exc:
            self.log_error("Could not read dashboard HTML: %s", exc)
            self.send_error(500, "Dashboard HTML file could not be read")
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != "/api/chat":
            self.send_error(404)
            return
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.send_json(400, {"error": "Invalid request length"})
            return
        if content_length <= 0 or content_length > MAX_REQUEST_BYTES:
            self.send_json(413, {"error": "Chat request is empty or too large"})
            return
        try:
            payload = json.loads(self.rfile.read(content_length))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self.send_json(400, {"error": "Request body must be valid JSON"})
            return
        if not isinstance(payload, dict):
            self.send_json(400, {"error": "Request body must be a JSON object"})
            return
        question = payload.get("question")
        evidence = payload.get("evidence")
        if not isinstance(question, str) or not question.strip() or len(question) > 1000:
            self.send_json(400, {"error": "Enter a question of at most 1,000 characters"})
            return
        if not isinstance(evidence, str) or not evidence.strip():
            self.send_json(400, {"error": "No matching school-data evidence was found"})
            return

        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            self.send_json(503, {"error": "Groq is not configured. Add GROQ_API_KEY to the local .env file and restart the server."})
            return

        system_prompt = (
            "You are an evidence-grounded analyst of Indian school education. "
            "Use only the supplied dashboard evidence for factual claims. Never invent figures, "
            "causes, missing years, or comparisons. If the evidence cannot answer part of the "
            "question, say so plainly. Distinguish observed facts, cautious interpretation, and "
            "practical recommendations. For summary questions, write a concise narrative about "
            "current status and direction of change; do not report row counts, column counts, or "
            "dataset dimensions. Keep suggestions relevant to schools and label them as proposals, "
            "not proven effects. Avoid claiming that correlation proves causation."
        )
        request_body = json.dumps({
            "model": MODEL,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": (
                    "Question:\n" + question.strip() + "\n\n"
                    "Evidence retrieved from the loaded school-education dataset:\n"
                    + evidence_as_text(evidence)
                )},
            ],
        }).encode("utf-8")
        request = Request(
            GROQ_URL,
            data=request_body,
            headers={
                "Authorization": "Bearer " + api_key,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=45) as response:
                result = json.loads(response.read().decode("utf-8"))
            answer = result["choices"][0]["message"]["content"]
            if not isinstance(answer, str) or not answer.strip():
                raise ValueError("Groq returned an empty answer")
        except HTTPError as exc:
            detail = exc.read(1200).decode("utf-8", errors="replace")
            self.log_error("Groq API returned HTTP %s: %s", exc.code, detail)
            self.send_json(502, {"error": "The Groq service rejected the request. Check the API key, model access, and account limits."})
            return
        except (URLError, TimeoutError) as exc:
            self.log_error("Groq API connection failed: %s", exc)
            self.send_json(502, {"error": "Could not reach Groq. Check the internet connection and try again."})
            return
        except (KeyError, IndexError, TypeError, json.JSONDecodeError, ValueError) as exc:
            self.log_error("Invalid Groq response: %s", exc)
            self.send_json(502, {"error": "Groq returned an unreadable response. Please try again."})
            return
        self.send_json(200, {"answer": answer, "model": MODEL})


def main():
    load_env_file()
    address = ("127.0.0.1", int(os.getenv("PORT", "8000")))
    server = ThreadingHTTPServer(address, DashboardHandler)
    print(f"Dashboard ready at http://{address[0]}:{address[1]}")
    print("Groq API key loaded." if os.getenv("GROQ_API_KEY") else "Groq is not configured; data-only answers remain available.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down dashboard server.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
