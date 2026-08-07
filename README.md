# OmniStock

Managing inventory with spreadsheets or scattered tools can quickly become confusing. Products go out of stock without warning, orders are oversold, and manual updates often lead to costly mistakes.

OmniStock is a single-organization Inventory Management and Order Processing system designed to simplify these tasks. It provides one centralized platform where retail teams can:

- Track products and inventory levels
- Manage suppliers
- Create and process customer orders
- Receive low-stock alerts before products run out
- Keep inventory accurate with automatic, atomic stock updates, even when multiple orders are placed at the same time

The project is built as a lightweight internal tool that is easy for employees to use every day while giving administrators the control they need through user roles, permissions, and an auditable order history.

---



## Getting Started

Follow these steps in order to get OmniStock running on your machine.

### Prerequisites

Before you start, make sure you have the following installed:

- **Python** (3.10+ recommended)
- **Git**
- **MySQL** — see [Install MySQL](#1-install-mysql) below if you don't have it yet



### 1. Clone the Repository

```bash
git clone git@github.com:AI-with-Coding-2026/Project-A-omnistock.git
cd Project-A-omnistock

```



### 2. Install MySQL

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



#### Create the project database

1. Open **MySQL Command Line Client** (Windows) or open Terminal and run `mysql -u root -p` (macOS), then log in with your root password.
2. Run the following command to create the project's database (same command on both operating systems):
  ```sql
  CREATE DATABASE omnistock;

  ```
3. Keep this database name (`omnistock`) and your root password handy — you'll enter them into the project's `.env` file in a later step.



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

Create a `.env` file inside the `venv` folder with the following content:

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



### 7. Start the Development Server

```bash
python manage.py runserver

```

The project should now be running locally — check your terminal output for the local URL (typically `http://127.0.0.1:8000/`).

### Quick Reference

```bash
git clone git@github.com:AI-with-Coding-2026/Project-A-omnistock.git
cd Project-A-omnistock
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux
pip install -r requirements.txt
# create .env in venv/ with your DB credentials
python manage.py migrate
python manage.py runserver

```

---



## Software Dependencies

OmniStock is a Django project split into three apps:

- `users` **(**`core`**)** — authentication, custom user model/roles, shared templates.
- `inventory` — Suppliers and Products.
- `orders` — Orders and Order Items.

Python package requirements (pinned in `requirements.txt`):


| Package               | Version |
| --------------------- | ------- |
| `Django`              | 6.0.7   |
| `djangorestframework` | 3.17.1  |
| `asgiref`             | 3.12.1  |
| `pillow`              | 12.3.0  |
| `PyMySQL`             | 1.2.0   |
| `python-decouple`     | 3.8     |
| `sqlparse`            | 0.5.5   |
| `tzdata`              | 2026.3  |


External requirement: **MySQL 8.x** (see [Install MySQL](#2-install-mysql) above).

---



## Latest Releases

This project doesn't have tagged releases yet. Check the Releases page on GitHub for updates once versioning starts.

---



## API Reference

OmniStock uses **Django REST Framework** for its API layer. Endpoints are still being finalized as development progresses through the sprint roadmap (custom auth → inventory views → order transactions → dashboards/exports). Once stable, endpoint documentation will be added here or linked to a dedicated `API.md` / DRF browsable API.

---



## Build and Test

Run the Django development checks and test suite from the project root (with your virtual environment active):

```bash
# Check for configuration issues
python manage.py check

# Run the test suite
python manage.py test

```

There is currently no separate frontend build step — templates are rendered server-side by Django.

---



## Contribute

Contributions are welcome. To contribute:

1. Fork the repository and create a feature branch:
  ```bash
  git checkout -b feature/your-feature-name

  ```
2. Follow the [Installation](#getting-started) steps above to set up your local environment.
3. Make your changes, following existing code style and adding tests where relevant.
4. Run `python manage.py test` to confirm nothing is broken.
5. Commit your changes and open a pull request describing what you changed and why.

For larger changes, please open an issue first to discuss what you'd like to change.