## Project Overview

This is a complete, production-like enterprise web system designed and implemented as the final project for a university Database Development course. It simulates a real-world corporate vehicle management workflow from request submission to trip completion, with strict role separation, audit trail capabilities, and a powerful administrative interface.

### Supported User Roles

| Role                       | utype in DB      | Main Functions                                             |
| -------------------------- | ---------------- | ---------------------------------------------------------- |
| Regular Employee / Manager | normal           | Submit & view trip requests                                |
| Approver                   | approver         | Approve/Reject requests, assign driver + vehicle           |
| Driver                     | driver           | View current & past trips, mark as In Progress / Completed |
| Database Administrator     | database_manager | Full read/write access to every table                      |

## Project Structure

```
vehicle-management-system/
│
├── app.py                  
├── seed.py                
├── 5003project.db          
├── templates/              
│   ├── login.html
│   ├── register.html
│   ├── user_dashboard.html
│   ├── approver_dashboard.html
│   ├── driver_dashboard.html
│   └── admin_dashboard.html
├── requirements.txt        
└── README.md               
```

## Dependencies

Only two external packages are required:

```
Flask==2.3.3
Faker==30.3.0
```

(standard library modules: sqlite3, datetime, random, re, etc.)

## How to Run the Project

### 1. Clone the repository

```
git clone https://github.com/yourusername/vehicle-management-system.git
cd vehicle-management-system
```

### 2. (Recommended) Create a virtual environment

```
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate
```

### 3. Install dependencies

```
pip install -r requirements.txt
pip install Flask Faker
```

### 4. Generate realistic test data

```
python seed.py
```

This script will:

- Clear any existing data
- Create 6 departments
- Generate ~129 employees (including managers, 15 drivers, 5 approvers, 1 DB admin)
- Insert 40 vehicles with realistic plates, brands, mileage, etc.
- Create 200 trip requests (past and future) with various statuses
- Set default password for all accounts: password123

### 5. Start the Flask server

```
python app.py
```

### 6. Open your browser

Go to: http://127.0.0.1:5000
