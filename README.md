<div align="center">

<img src="https://raw.githubusercontent.com/AI-with-Coding-2026/Project-A-omnistock/main/core/static/core/logo.svg" alt="OmniStock Logo" width="90" />

# OmniStock

### Inventory. Orders. Suppliers. One workspace.

[![Typing SVG](https://readme-typing-svg.demolab.com?font=Fira+Code&size=20&pause=1000&color=1F9D6B&center=true&vCenter=true&width=600&lines=Track+products+and+stock+levels;Never+oversell+again;Automatic%2C+atomic+stock+updates;Built+for+retail+teams)](https://git.io/typing-svg)

![Django](https://img.shields.io/badge/Django-6.0.7-0C4B33?style=for-the-badge&logo=django&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)
![MySQL](https://img.shields.io/badge/MySQL-8.x-4479A1?style=for-the-badge&logo=mysql&logoColor=white)
![DRF](https://img.shields.io/badge/DRF-3.17.1-A30000?style=for-the-badge&logo=django&logoColor=white)
![License](https://img.shields.io/badge/status-internal--tool-6b7280?style=for-the-badge)

</div>

---

## 📦 What is OmniStock?

Managing inventory with spreadsheets or scattered tools can quickly become confusing. Products go out of stock without warning, orders are oversold, and manual updates often lead to costly mistakes.

OmniStock is a single-organization **Inventory Management and Order Processing system** designed to simplify these tasks. It provides one centralized platform where retail teams can:

- 📊 Track products and inventory levels
- 🚚 Manage suppliers
- 🧾 Create and process customer orders
- 🔔 Receive low-stock alerts before products run out
- ⚡ Keep inventory accurate with automatic, atomic stock updates, even when multiple orders are placed at the same time

The project is built as a lightweight internal tool that is easy for employees to use every day while giving administrators the control they need through user roles, permissions, and an auditable order history. A public landing page introduces the product to first-time visitors before they log in.

---

## 🚀 Getting Started

Follow these steps in order to get OmniStock running on your machine.

### Prerequisites

Before you start, make sure you have the following installed:

- **Python** (3.10+ recommended)
- **Git**
- **MySQL** — see [Install MySQL](#2-install-mysql) below if you don't have it yet

### 1. Clone the Repository

```bash
git clone git@github.com:AI-with-Coding-2026/Project-A-omnistock.git
cd Project-A-omnistock
```

<details>
<summary><b>2. Install MySQL</b> — click to expand</summary>

<br>

MySQL is where the project's data will be stored.

1. Go to [dev.mysql.com/downloads/mysql](https://dev.mysql.com/downloads/mysql/).
2. **Windows:** Download `mysql-installer-community` (the larger `.msi` file). Run it and choose the **Developer Default** setup type when prompted.
3. **macOS:** Download the `.dmg` file, open it, and run the installer package. Alternatively, install it via Homebrew:
```bash
   brew install mysql
```
4. Follow the prompts. When asked to set a root password, choose something simple you'll remember (write it down) — you'll need it shortly.
5. Finish the installation and make sure the MySQL service is running:
   - **Windows:** starts automatically.
   - **macOS:** start it via System Settings, or run:
```bash
     brew services start mysql
```

**Create the project database:**

1. Open **MySQL Command Line Client** (Windows) or open Terminal and run `mysql -u root -p` (macOS), then log in with your root password.
2. Run the following command to create the project's database (same command on both operating systems):
```sql
   CREATE DATABASE omnistock;
```
3. Keep this database name (`omnistock`) and your root password handy — you'll enter them into the project's `.env` file in a later step.

</details>

### 3. Create and Activate a Virtual Environment

From the project root:

```bash
python -m venv venv
```

Activate it:

- **Windows (PowerShell):**
```powershell
  venv\Scripts\activate
```
- **macOS/Linux:**
```bash
  source venv/bin/activate
```

You should see `(venv)` appear at the start of your terminal prompt once it's active.

### 4. Install Dependencies

With the virtual environment active, install the required packages:

```bash
pip install -r requirements.txt
```

### 5. Configure Environment Variables

Create a `.env` file in the **project root directory** (next to `manage.py`) with the following content:

```env
DB_NAME=omnistock
DB_USER=root
DB_PASSWORD=<your MySQL root password>
DB_HOST=127.0.0.1
DB_PORT=3306
```

Replace `<your MySQL root password>` with the root password you set during MySQL installation.

### 6. Run Migrations

Apply the database migrations to set up the schema:

```bash
python manage.py migrate
```

### 7. Collect Static Files

> ⚠️ **Don't skip this** — static assets (including the OmniStock logo) are served through Whitenoise using a hashed manifest for cache-busting.

```bash
python manage.py collectstatic --noinput
```

Run this once after setup, and again any time static files (CSS, images, icons) change. Skipping this step will cause images and some assets to 404 locally.

### 8. Seed Demo Data

```bash
python manage.py seed_db
```

The command creates:

* 👤 4 active demo users across Admin, Sales Rep, Inventory Manager, and Staff roles
* 🚚 10 suppliers with valid phone numbers
* 📦 40 products, including low-stock products
* 🧾 30 historical orders across Pending, Completed, and Cancelled statuses

Safe to run multiple times in a development environment — existing demo records are updated or refreshed instead of being duplicated.

<details>
<summary><b>🔑 Demo Login Accounts</b> — click to expand</summary>

<br>

All demo accounts use the password:

```text
demo12345
```

| Role              | Username            | Password    |
| ----------------- | -------------------- | ----------- |
| Admin             | `admin`              | `demo12345` |
| Sales Rep         | `sales_rep`          | `demo12345` |
| Inventory Manager | `inventory_manager`  | `demo12345` |
| Staff             | `staff`               | `demo12345` |

Use these accounts to test the different role-based views and permissions in OmniStock.

</details>

### 9. Start the Development Server

```bash
python manage.py runserver
```

🎉 The project should now be running locally — check your terminal output for the local URL (typically `http://127.0.0.1:8000/`). Anonymous visitors land on the public landing page; logging in redirects to the role-based dashboard.

<details>
<summary><b>⚡ Quick Reference</b> — full setup in one block</summary>

<br>

```bash
git clone git@github.com:AI-with-Coding-2026/Project-A-omnistock.git
cd Project-A-omnistock
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux
pip install -r requirements.txt
# create .env in the project root (next to manage.py) with your DB credentials
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py seed_db
python manage.py runserver
```

</details>

---

## 🧩 Software Dependencies

OmniStock is a Django project split into three apps:

| App | Responsibility |
|---|---|
| `core` (`users`) | Authentication, custom user model/roles, public landing page, shared templates |
| `inventory` | Suppliers and Products |
| `orders` | Orders and Order Items |

<details>
<summary><b>📋 Full package list</b> — click to expand</summary>

<br>

| Package               | Version |
| ---------------------- | ------- |
| `Django`               | 6.0.7   |
| `djangorestframework`  | 3.17.1  |
| `asgiref`              | 3.12.1  |
| `pillow`               | 12.3.0  |
| `PyMySQL`              | 1.2.0   |
| `python-decouple`      | 3.8     |
| `sqlparse`             | 0.5.5   |
| `tzdata`               | 2026.3  |
| `xhtml2pdf`            | 0.2.17  |
| `Faker`                | 40.37.0 |
| `dj-database-url`      | 3.1.2   |
| `gunicorn`             | 26.2.0  |
| `psycopg2-binary`      | 2.9.12  |
| `whitenoise`           | 6.12.0  |

</details>

External requirement: **MySQL 8.x** for local development. Production deployments may target PostgreSQL via `dj-database-url` and `psycopg2-binary`; served through `gunicorn` with static files handled by `whitenoise`.

---

## 🏷️ Latest Releases

This project doesn't have tagged releases yet. Check the Releases page on GitHub for updates once versioning starts.

---

## 🔌 API Reference

OmniStock uses **Django REST Framework** for its API layer. Endpoints are still being finalized as development progresses through the sprint roadmap (custom auth → inventory views → order transactions → dashboards/exports). Once stable, endpoint documentation will be added here or linked to a dedicated `API.md` / DRF browsable API.

---

## ✅ Build and Test

Run the Django development checks and test suite from the project root (with your virtual environment active):

```bash
# Check for configuration issues
python manage.py check

# Run the test suite
python manage.py test
```

There is currently no separate frontend build step — templates are rendered server-side by Django, styled with Tailwind CSS loaded via CDN.

---

## 🤝 Contribute

Contributions are welcome. To contribute:

1. All feature branches are pre-created on GitHub — check out your assigned branch as described in [WORKFLOW.md](WORKFLOW.md) rather than creating a new one:
```bash
   git fetch origin
   git checkout feature/[your-task-id]-[description]
   git pull origin main
```
2. Follow the [Installation](#-getting-started) steps above to set up your local environment.
3. Make your changes, following existing code style and adding tests where relevant.
4. Run `python manage.py test` to confirm nothing is broken.
5. Commit your changes and open a pull request describing what you changed and why. See [WORKFLOW.md](WORKFLOW.md) for full commit, PR, and merge-conflict guidelines.

For larger changes, please open an issue first to discuss what you'd like to change.

<div align="center">

---

Made with 🧠 by the OmniStock team

</div>
