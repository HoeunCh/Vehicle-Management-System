import sqlite3
import random
import re
from datetime import datetime, timedelta
from faker import Faker

# 初始化 Faker，使用英文环境
fake = Faker('en_US')

DATABASE = '5003project.db'

# 定义枚举常量
ROLES = ['employee', 'manager', 'driver', 'approver', 'database_manager']
USER_TYPES = {
    'employee': 'normal',
    'manager': 'normal',
    'driver': 'driver',
    'approver': 'approver',
    'database_manager': 'database_manager'
}
VEHICLE_STATUSES = ['available', 'assigned', 'maintenance', 'scrapped']

# 注意：Schema中存在中文逗号导致约束问题，为避免报错，仅使用前两个确定的目的
TRIP_PURPOSES = ['business trip', 'company tour']
# TRIP_PURPOSES = ['business trip', 'company tour', 'cargo transport', 'client pickup']

TRIP_STATUSES = ['Pending', 'Approved', 'Rejected', 'Completed', 'Cancelled']


def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    # 暂时关闭外键约束以便清理和插入循环依赖数据
    conn.execute("PRAGMA foreign_keys = OFF")
    return conn


def get_clean_phone():
    """生成只包含数字和括号的电话号码"""
    while True:
        raw_phone = fake.phone_number()
        # 使用正则只保留数字和括号
        clean_phone = re.sub(r'[^\d()]', '', raw_phone)
        # 确保生成的号码长度合理
        if len(clean_phone) > 7:
            return clean_phone


def clean_database(conn):
    """清空现有数据"""
    print("正在清空旧数据...")
    # 注意表名必须与数据库完全一致
    tables = ['trip_requests', 'vehicles', 'users', 'employees', 'departments']
    cursor = conn.cursor()
    for table in tables:
        try:
            cursor.execute(f"DELETE FROM {table}")
            cursor.execute(f"DELETE FROM sqlite_sequence WHERE name='{table}'")  # 重置自增ID
        except sqlite3.Error as e:
            print(f"提示: 清理表 {table} 时遇到状态: {e}")
    conn.commit()
    print("旧数据已清空。")


def create_departments(conn):
    """创建部门"""
    print("正在生成部门...")
    cursor = conn.cursor()
    departments = ['Human Resources', 'Sales', 'IT Department', 'Logistics', 'Finance', 'Marketing']
    dept_ids = []

    for dname in departments:
        while True:
            try:
                # 暂时将 manager_id 设为 0，因为员工还没生成
                dphone = get_clean_phone()
                cursor.execute(
                    "INSERT INTO departments (dname, manager_id, dphone) VALUES (?, ?, ?)",
                    (dname, 0, dphone)
                )
                dept_ids.append(cursor.lastrowid)
                break
            except sqlite3.IntegrityError:
                continue

    conn.commit()
    return dept_ids


def create_employees_and_users(conn, dept_ids):
    """创建员工和对应的用户账号"""
    print("正在生成员工和用户账号...")
    cursor = conn.cursor()

    employees = []
    drivers = []
    approvers = []

    # 1. 确保每个部门至少有一个经理
    for did in dept_ids:
        eid = insert_employee(cursor, did, 'manager')
        # 更新部门表，设置经理ID
        cursor.execute("UPDATE departments SET manager_id = ? WHERE did = ?", (eid, did))
        employees.append({'eid': eid, 'role': 'manager', 'did': did})

    # 2. 生成一些特定角色
    # 15个司机
    for _ in range(15):
        did = random.choice(dept_ids)
        eid = insert_employee(cursor, did, 'driver')
        employees.append({'eid': eid, 'role': 'driver', 'did': did})
        drivers.append(eid)

    # 5个审批员
    for _ in range(5):
        did = random.choice(dept_ids)
        eid = insert_employee(cursor, did, 'approver')
        employees.append({'eid': eid, 'role': 'approver', 'did': did})
        approvers.append(eid)

    # 1个数据库管理员
    did = random.choice(dept_ids)
    eid = insert_employee(cursor, did, 'database_manager')
    employees.append({'eid': eid, 'role': 'database_manager', 'did': did})

    # 3. 增加大量普通员工 (100人)
    for _ in range(100):
        did = random.choice(dept_ids)
        eid = insert_employee(cursor, did, 'employee')
        employees.append({'eid': eid, 'role': 'employee', 'did': did})

    conn.commit()
    return employees, drivers, approvers


def insert_employee(cursor, did, role):
    """插入单个员工并创建对应User的辅助函数"""
    while True:
        try:
            fname = fake.first_name()
            lname = fake.last_name()
            email = f"{fname.lower()}.{lname.lower()}{random.randint(100, 999)}@company.com"
            phone = get_clean_phone()
            join_date = fake.date_between(start_date='-5y', end_date='today')

            # 插入 Employee
            cursor.execute('''
                INSERT INTO employees (fname, lname, ephone, email, role, did, e_is_active, join_date)
                VALUES (?, ?, ?, ?, ?, ?, 1, ?)
            ''', (fname, lname, phone, email, role, did, join_date))
            eid = cursor.lastrowid

            # 插入 User
            username = f"{fname.lower()}{random.randint(1, 9999)}"
            password = "password123"
            utype = USER_TYPES.get(role, 'normal')

            cursor.execute('''
                INSERT INTO users (username, password, eid, u_is_active, utype)
                VALUES (?, ?, ?, 1, ?)
            ''', (username, password, eid, utype))

            return eid

        except sqlite3.IntegrityError:
            continue


def create_vehicles(conn):
    """创建车辆"""
    print("正在生成车辆...")
    cursor = conn.cursor()

    brands = [
        ('Toyota', ['Camry', 'HiAce', 'Coaster']),
        ('Ford', ['Transit', 'F-150']),
        ('Honda', ['Odyssey', 'CR-V']),
        ('Mercedes', ['Sprinter', 'V-Class'])
    ]
    colors = ['White', 'Black', 'Silver', 'Blue', 'Red']

    vehicle_ids = []

    created_count = 0
    while created_count < 40:
        brand_data = random.choice(brands)
        brand = brand_data[0]
        model = random.choice(brand_data[1])
        color = random.choice(colors)

        plate_letters = "".join(random.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ", k=3))
        plate_nums = "".join(random.choices("0123456789", k=4))
        plate = f"{plate_letters}-{plate_nums}"

        capacity = random.choice([4, 6, 7, 15, 20])
        status = random.choice(['available', 'available', 'available', 'maintenance', 'assigned'])
        mileage = round(random.uniform(1000, 150000), 2)
        fuel = round(random.uniform(10, 60), 2)

        try:
            cursor.execute('''
                INSERT INTO vehicles (plate, brand, model, capacity, color, vstatus, current_mileage, fuel)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (plate, brand, model, capacity, color, status, mileage, fuel))
            vehicle_ids.append(cursor.lastrowid)
            created_count += 1
        except sqlite3.IntegrityError:
            continue

    conn.commit()
    return vehicle_ids


def create_trip_requests(conn, employees, drivers, approvers, vehicle_ids):
    """生成行程申请历史"""
    print("正在生成行程记录...")
    cursor = conn.cursor()

    for _ in range(200):
        requester = random.choice(employees)
        eid = requester['eid']

        purpose = random.choice(TRIP_PURPOSES)
        destination = fake.address().replace('\n', ', ')
        num_passengers = random.randint(1, 10)

        is_past = random.choice([True, True, False])
        if is_past:
            start_time = fake.date_time_between(start_date='-60d', end_date='now')
            status_choices = ['Completed', 'Rejected', 'Cancelled']
        else:
            start_time = fake.date_time_between(start_date='now', end_date='+30d')
            status_choices = ['Pending', 'Approved']

        duration_hours = random.randint(1, 48)
        end_time = start_time + timedelta(hours=duration_hours)

        start_str = start_time.strftime('%Y-%m-%d %H:%M:%S')
        end_str = end_time.strftime('%Y-%m-%d %H:%M:%S')

        current_status = random.choice(status_choices)

        approver_id = None
        driver_id = None
        vid = None

        if current_status in ['Approved', 'Completed']:
            if approvers:
                approver_id = random.choice(approvers)
            if drivers:
                driver_id = random.choice(drivers)
            if vehicle_ids:
                vid = random.choice(vehicle_ids)

        elif current_status == 'Rejected':
            if approvers:
                approver_id = random.choice(approvers)

        try:
            # 确保表名是 trip_requests
            cursor.execute('''
                INSERT INTO trip_requests 
                (eid, purpose, destination, start_time, end_time, num_passengers, current_status, approver_id, driver_id, vid)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
            eid, purpose, destination, start_str, end_str, num_passengers, current_status, approver_id, driver_id, vid))
        except sqlite3.Error as e:
            print(f"插入行程记录失败: {e}")
            # 如果是表名错误，在这里会打印出来
            break

    conn.commit()


def main():
    conn = None
    try:
        conn = get_db_connection()
        print(f"成功连接到数据库: {DATABASE}")

        # 1. 清理旧数据
        clean_database(conn)

        # 2. 生成部门
        dept_ids = create_departments(conn)
        print(f"生成了 {len(dept_ids)} 个部门")

        # 3. 生成员工和用户
        employees, drivers, approvers = create_employees_and_users(conn, dept_ids)
        print(f"生成了 {len(employees)} 名员工")
        print(f" - 其中司机: {len(drivers)} 名")
        print(f" - 其中审批员: {len(approvers)} 名")

        # 4. 生成车辆
        vehicle_ids = create_vehicles(conn)
        print(f"生成了 {len(vehicle_ids)} 辆车")

        # 5. 生成行程记录
        create_trip_requests(conn, employees, drivers, approvers, vehicle_ids)

        # 重新启用外键检查
        conn.execute("PRAGMA foreign_keys = ON")

        print("\n=== 数据生成完成! ===")
        print("所有用户的初始密码均为: password123")

    except Exception as e:
        print(f"\n发生错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if conn:
            conn.close()


if __name__ == '__main__':
    main()