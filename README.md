# 🏆 Kendo Tournament Group Draw API

This project provides a **Flask-based REST API** and simple web UI for
performing **group draws** for tournaments (such as Kendo events). It allows
uploading lists of competitors and groups, defining fixed positions, and then
running a **systematic draw algorithm** that minimizes country-based collisions
(i.e., competitors from the same country being placed in the same group).

---

## 📋 Features

- Upload competitors, groups, and fixed positions through JSON APIs.
- Validate data consistency before the draw.
- Automatically assign competitors to groups while minimizing same-country
  collisions.
- Optionally fix specific competitors to positions (e.g., seeded players).
- Export results in JSON or CSV format.
- Web interface.

---

## ⚙️ Requirements

- **Python 3.9+** is recommended.
- **uv** (for pip, install dependencies before)

---

## 🚀 Running the Application

1. **Clone this repository** (or copy the script into a file):

   ```bash
   git clone https://github.com/xlittlerag/groups_assigner.git
   cd groups_assigner
   ```

2. **Run the Flask server:**

   ```bash
   uv run main.py
   ```

3. The API will start on:

   ```
   http://localhost:5000
   ```

4. Open your browser and go to [http://127.0.0.1:5000](http://127.0.0.1:5000) to
   access the web UI.

---

## 🧠 Algorithm Overview

The assignment process uses a **systematic algorithm** designed to minimize
country collisions:

1. Fixed positions are applied first.
2. Competitors are grouped by country.
3. Countries with the most competitors are distributed first.
4. Each competitor is placed into groups with the fewest from their country.
5. Multiple random seeds can be tested (when `minimization=True`) to find the
   optimal configuration.
6. The configuration with the fewest country collisions is returned.

---

## 📁 Project Structure

```
project/
│
├── main.py                # Main Flask application
├── templates/
│   └── index.html        # Web interface template
└── README.md             # Documentation
```

---

## 🧩 Example Workflow

1. Upload competitors
2. Upload groups
3. Optionally upload fixed positions
4. Validate all inputs
5. Run the draw
6. Export results

---

## 🏁 License

MIT License © 2025 You are free to use, modify, and distribute this software
with attribution.
