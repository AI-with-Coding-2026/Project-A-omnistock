 # 🚀 OmniStock — Developer Workflow & Git Rules
 
 
 Dear Team,
 To keep our development process smooth, maintain a clean codebase, and prevent any git conflicts, **everyone must strictly follow this guide**.
 All task feature branches have been **pre-created on GitHub**. You do **NOT** need to create any new branches yourself.

 ---

## 🚨 3 Mandatory Git Rules

1. **Always Pull First:** Run `git pull origin main` before creating branches, pushing, or starting any branch work to avoid reverting fixes.
2. **Test Thoroughly:** Test your code manually on the actual UI across relevant user roles (Admin, Sales, Inventory)—don't just check if the app runs.
3. **PR Testing Note:** Every Pull Request description MUST include a short note explaining how it was tested (e.g., *"Tested login and product creation using Admin and Sales roles"*).
 ---
 
 
 ## 📌 1. Active Sprint 2 Branch Assignments

Locate your assigned Sprint 2 task below and checkout your pre-created branch:

* **Supplier Index page:** `feature/s2-supplier-index` (Ashenafi & Rostel)
* **Supplier Create/Edit:** `feature/s2-supplier-create-edit` (Rostel & Ashenafi)
* **Product Index page:** `feature/s2-product-index` (Masimbonge & Rayan)
* **Product Create page:** `feature/s2-product-create` (Rayan & Masimbonge)
* **Product Edit page:** `feature/s2-product-edit` (Farhan & Salman)
* **Low-stock detection logic:** `feature/s2-low-stock-logic` (Salman & Farhan)
* **Low-stock dashboard card:** `feature/s2-low-stock-card` (Christian & Fatima)
* **Order Create + dynamic line items:** `feature/s2-order-create-items` (Sara & Muhammet)
* **Stock validation on order entry:** `feature/s2-stock-validation` (Muhammet & Sara)
 
 
 ---
 
 
 ## 🔄 2. Step-by-Step Daily Workflow
 
 
 ### **Step A: Start Working (Checkout your branch)**
 
 
 Always update your local repository and switch to your branch:
 ```bash
 # 1. Get the latest branches from GitHub
 git fetch origin
 
 # 2. Switch to your assigned feature branch
 git checkout feature/[your-task-id]-[description]
 
 # 3. Sync your branch with latest main
 git pull origin main
 
 ```
 
 
 ---
 
 
 ### **Step B: Save Progress (Committing Work)**
 
 
 Make small, clear commits as you work:
 ```bash
 git add .
 git commit -m "feat(task-id): add user model and fields"
 
 ```
 
 
 ---
 
 
 ### **Step C: Push & Open a Pull Request (PR)**
 
 
 When your task is completed and tested locally:
 ```bash
 # Push your code to your remote branch
 git push origin feature/[your-s2-branch-name]
 
 ```
 
 
 1. Go to **GitHub Repository** ➔ Click on **Pull Requests**.
 2. Open a new PR targeting the `main` branch.
 3. Include the testing note in the PR description explaining how you tested the feature.
 4. Assign **Rayan** as a **Reviewer**.
 5. 🛑 **Do NOT merge your own PR.** Wait for review and approval.
 
 
 ---
 
 
 ## ⚠️ 3. Crucial Rules & Trouble-Shooting
 
 
 ### 🛡️ Rule 1: NEVER `git pull` with Unsaved Changes!
 
 
 Before pulling updates or switching branches, **always save your local changes**. Otherwise, Git will block you or overwrite your work.
 * **Option 1 (Commit):** `git add .` then `git commit -m "WIP: saving progress"`
 * **Option 2 (Stash):** `git stash` ➔ do your pull ➔ `git stash pop`
 
 
 ### 🚫 Rule 2: Files You Must NEVER Commit
 
 
 Do not upload temporary environment or system files:
 * `.env` (Environment variables)
 * `.venv/` or `env/` (Virtual environment)
 * `db.sqlite3` (Local database)
 * `__pycache__/`
 
 
 ### 💥 Rule 3: Handling Merge Conflicts
 
 
 If GitHub says *"Cannot automatically merge"*:
 1. Stay on your feature branch locally.
 2. Run: `git pull origin main`
 3. Open Cursor, resolve the conflict highlights manually, and test your app.
 4. Commit and push again:
 ```bash
 git add .
 git commit -m "fix: resolve merge conflicts with main"
 git push origin feature/[your-branch-name]
 
 ```
 
 
 
 
 ---
 
 📦 Archive: Completed Sprint 1 Branches (Reference Only)
Task 2291: feature/2291-django-setup (Rostel & Christian)

Task 2418: feature/2418-roles-migrations (Rostel & Christian)
Task 2293: feature/2293-define-user-roles (Rostel & Christian)
Task 2294: feature/2294-role-permissions-matrix (Ashenafi)
Task 2296: feature/2296-permission-middleware (Bilal & Muhammet)
Task 2297: feature/2297-apply-route-middleware (Bilal & Muhammet)
Task 2298: feature/2298-users-migration (Rayan & Ashenafi)
Task 2299: feature/2299-suppliers-migration (Rayan & Ashenafi)
Task 2300: feature/2300-products-migration (Rayan & Ashenafi)
Task 2301: feature/2301-orders-migration (Rayan & Ashenafi)
Task 2302: feature/2302-order-items-migration (Rayan & Ashenafi)
Task 2303: feature/2303-invoices-migration (Rayan & Ashenafi)
Task 2305: feature/2305-supplier-seeder (Baya & Sara)
Task 2306: feature/2306-product-seeder (Baya & Sara)
Task 2307: feature/2307-users-seeder (Baya & Sara)
Task 2315: feature/2315-role-redirect-login (Baya & Sara)
Task 2308: feature/2308-master-layout (Salman & Fatima)
Task 2309: feature/2309-layout-styling (Salman & Fatima)
Task 2311: feature/2311-role-based-nav (Farhan & Masimbongwe)
Task 2314: feature/2314-login-ui-auth (Salman)
Task 2318: feature/2318-dashboard-cards (Fatima)

*Thank you all! Let’s build something amazing together in Sprint 2! 🚀*

