from flask import Flask, request, jsonify, session, redirect, url_for, render_template, send_file
import sqlite3
import os
import json
from datetime import datetime
import io

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
DATABASE = '5003project.db'


def get_db_connection():
    """获取数据库连接"""
    conn = sqlite3.connect(DATABASE, timeout=10.0)  # 添加超时设置
    conn.row_factory = sqlite3.Row
    # 启用外键约束
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# 登录页面
@app.route('/')
def index():
    return render_template('login.html')


# 登录处理
@app.route('/login', methods=['POST'])
def login():
    username = request.form['username']
    password = request.form['password']
    user_id = request.form.get('user_id')
    user_type = request.form.get('user_type')

    # 验证用户ID是否为数字
    try:
        user_id_int = int(user_id)
    except (ValueError, TypeError):
        return render_template('login.html', error='Invalid user ID format')

    conn = get_db_connection()
    user = conn.execute('''
        SELECT u.*, e.fname, e.lname 
        FROM users u 
        JOIN employees e ON u.eid = e.eid 
        WHERE u.username = ? AND u.password = ? AND u.u_is_active = 1
    ''', (username, password)).fetchone()
    conn.close()

    if user:
        # 验证用户ID和用户类型是否匹配
        if user['uid'] != user_id_int:
            return render_template('login.html', error='User ID does not match the username')

        if user['utype'] != user_type:
            return render_template('login.html', error='User type does not match the username')

        session['user_id'] = user['uid']
        session['username'] = user['username']
        session['user_type'] = user['utype']
        session['full_name'] = f"{user['fname']} {user['lname']}"

        # 根据用户类型重定向
        if user['utype'] == 'normal':
            return redirect(url_for('user_dashboard'))
        elif user['utype'] == 'approver':
            return redirect(url_for('approver_dashboard'))
        elif user['utype'] == 'driver':
            return redirect(url_for('driver_dashboard'))
        elif user['utype'] == 'database_manager':
            return redirect(url_for('admin_dashboard'))

    return render_template('login.html', error='Invalid username or password')


# 普通用户仪表板
@app.route('/user/dashboard')
def user_dashboard():
    if 'user_id' not in session or session['user_type'] != 'normal':
        return redirect(url_for('index'))

    conn = get_db_connection()

    # 获取当前用户的员工ID
    user_info = conn.execute(
        'SELECT eid FROM users WHERE uid = ?', (session['user_id'],)
    ).fetchone()

    requests = conn.execute('''
        SELECT tr.*, e.fname, e.lname 
        FROM trip_requests tr 
        JOIN employees e ON tr.eid = e.eid 
        WHERE tr.eid = ? 
        ORDER BY tr.created_at DESC
    ''', (user_info['eid'],)).fetchall()
    conn.close()

    return render_template('user_dashboard.html', requests=requests)


# 提交新申请 - 修改版本，添加备注字段
@app.route('/user/new_request', methods=['POST'])
def new_request():
    if 'user_id' not in session or session['user_type'] != 'normal':
        return jsonify({'success': False, 'message': 'Unauthorized access'})

    data = request.json
    conn = get_db_connection()

    try:
        # 获取当前用户的员工ID
        user_info = conn.execute(
            'SELECT eid FROM users WHERE uid = ?', (session['user_id'],)
        ).fetchone()

        # 随机选择一个审核员
        approver = conn.execute('''
            SELECT uid FROM users 
            WHERE utype = 'approver' AND u_is_active = 1 
            ORDER BY RANDOM() LIMIT 1
        ''').fetchone()

        if not approver:
            return jsonify({'success': False, 'message': 'No available approvers'})

        # 插入新请求并分配审核员，包含备注
        conn.execute('''
            INSERT INTO trip_requests (eid, purpose, destination, start_time, end_time, passenger_number, approved_by, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            user_info['eid'],
            data['purpose'],
            data['destination'],
            data['start_time'],
            data['end_time'],
            data['passenger_number'],
            approver['uid'],  # 随机分配的审核员
            data.get('notes', '')  # 获取备注信息，如果没有则为空字符串
        ))
        conn.commit()
        return jsonify({'success': True, 'message': 'Request submitted successfully'})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': f'Submission failed: {str(e)}'})
    finally:
        conn.close()


# 审批员仪表板 - 完善版本
@app.route('/approver/dashboard')
def approver_dashboard():
    if 'user_id' not in session or session['user_type'] != 'approver':
        return redirect(url_for('index'))

    conn = get_db_connection()

    # 获取分配给当前审批员的待审批请求
    pending_requests = conn.execute('''
        SELECT tr.*, e.fname, e.lname, d.dname 
        FROM trip_requests tr 
        JOIN employees e ON tr.eid = e.eid 
        JOIN departments d ON e.did = d.did 
        WHERE tr.current_status = 'pending' AND tr.approved_by = ?
        ORDER BY tr.created_at DESC
    ''', (session['user_id'],)).fetchall()

    # 获取已分配的请求
    assigned_requests = conn.execute('''
        SELECT tr.*, e.fname, e.lname, d.dname, 
               v.plate as vehicle_plate, v.brand as vehicle_brand,
               driver.fname as driver_fname, driver.lname as driver_lname
        FROM trip_requests tr 
        JOIN employees e ON tr.eid = e.eid 
        JOIN departments d ON e.did = d.did 
        LEFT JOIN vehicles v ON tr.assigned_vid = v.vid
        LEFT JOIN employees driver ON tr.assigned_eid = driver.eid
        WHERE tr.current_status = 'assigned' AND tr.approved_by = ?
        ORDER BY tr.created_at DESC
    ''', (session['user_id'],)).fetchall()

    # 获取进行中的请求
    in_progress_requests = conn.execute('''
        SELECT tr.*, e.fname, e.lname, d.dname, 
               v.plate as vehicle_plate, v.brand as vehicle_brand,
               driver.fname as driver_fname, driver.lname as driver_lname
        FROM trip_requests tr 
        JOIN employees e ON tr.eid = e.eid 
        JOIN departments d ON e.did = d.did 
        LEFT JOIN vehicles v ON tr.assigned_vid = v.vid
        LEFT JOIN employees driver ON tr.assigned_eid = driver.eid
        WHERE tr.current_status = 'in_progress' AND tr.approved_by = ?
        ORDER BY tr.created_at DESC
    ''', (session['user_id'],)).fetchall()

    # 获取已完成的请求
    completed_requests = conn.execute('''
        SELECT tr.*, e.fname, e.lname, d.dname, 
               v.plate as vehicle_plate, v.brand as vehicle_brand,
               driver.fname as driver_fname, driver.lname as driver_lname
        FROM trip_requests tr 
        JOIN employees e ON tr.eid = e.eid 
        JOIN departments d ON e.did = d.did 
        LEFT JOIN vehicles v ON tr.assigned_vid = v.vid
        LEFT JOIN employees driver ON tr.assigned_eid = driver.eid
        WHERE tr.current_status = 'completed' AND tr.approved_by = ?
        ORDER BY tr.created_at DESC
    ''', (session['user_id'],)).fetchall()

    # 获取已拒绝的请求
    rejected_requests = conn.execute('''
        SELECT tr.*, e.fname, e.lname, d.dname 
        FROM trip_requests tr 
        JOIN employees e ON tr.eid = e.eid 
        JOIN departments d ON e.did = d.did 
        WHERE tr.current_status = 'rejected' AND tr.approved_by = ?
        ORDER BY tr.created_at DESC
    ''', (session['user_id'],)).fetchall()

    # 获取已取消的请求
    cancelled_requests = conn.execute('''
        SELECT tr.*, e.fname, e.lname, d.dname 
        FROM trip_requests tr 
        JOIN employees e ON tr.eid = e.eid 
        JOIN departments d ON e.did = d.did 
        WHERE tr.current_status = 'cancelled' AND tr.approved_by = ?
        ORDER BY tr.created_at DESC
    ''', (session['user_id'],)).fetchall()

    conn.close()

    return render_template('approver_dashboard.html',
                           requests=pending_requests,
                           assigned_requests=assigned_requests,
                           in_progress_requests=in_progress_requests,
                           completed_requests=completed_requests,
                           rejected_requests=rejected_requests,
                           cancelled_requests=cancelled_requests)


# 处理审批 - 完善版本，添加拒绝理由存储，并修复司机随机分配问题，添加时间冲突检测
@app.route('/approver/process_request', methods=['POST'])
def process_request():
    if 'user_id' not in session or session['user_type'] != 'approver':
        return jsonify({'success': False, 'message': 'Unauthorized access'})

    data = request.json
    request_id = data['request_id']
    action = data['action']
    reject_reason = data.get('reject_reason', '')

    conn = get_db_connection()

    try:
        # 首先验证这个请求是否分配给当前审批员
        request_check = conn.execute(
            'SELECT approved_by FROM trip_requests WHERE rid = ?',
            (request_id,)
        ).fetchone()

        if not request_check or request_check['approved_by'] != session['user_id']:
            return jsonify({'success': False, 'message': 'Unauthorized to process this request'})

        if action == 'approve':
            # 获取当前请求的时间信息
            current_request = conn.execute(
                'SELECT start_time, end_time FROM trip_requests WHERE rid = ?',
                (request_id,)
            ).fetchone()

            if not current_request:
                return jsonify({'success': False, 'message': 'Request not found'})

            start_time = current_request['start_time']
            end_time = current_request['end_time']

            # 随机分配可用车辆
            vehicle = conn.execute(
                "SELECT vid FROM vehicles WHERE vstatus = 'available' ORDER BY RANDOM() LIMIT 1"
            ).fetchone()

            if not vehicle:
                return jsonify({'success': False, 'message': 'No available vehicles'})

            # 查找没有时间冲突的可用司机
            available_drivers = conn.execute('''
                SELECT u.eid 
                FROM users u 
                JOIN employees e ON u.eid = e.eid 
                WHERE u.utype = 'driver' 
                AND u.u_is_active = 1
                AND e.e_is_active = 1
                AND u.eid NOT IN (
                    SELECT tr.assigned_eid 
                    FROM trip_requests tr
                    WHERE tr.current_status IN ('assigned', 'in_progress')
                    AND tr.assigned_eid IS NOT NULL
                    AND (
                        (tr.start_time <= ? AND tr.end_time >= ?) OR
                        (tr.start_time <= ? AND tr.end_time >= ?) OR
                        (tr.start_time >= ? AND tr.end_time <= ?)
                    )
                )
                ORDER BY RANDOM() LIMIT 1
            ''', (start_time, start_time, end_time, end_time, start_time, end_time)).fetchone()

            if not available_drivers:
                # 如果没有完全空闲的司机，尝试找时间冲突最少的司机
                # 这里可以扩展为更复杂的调度算法
                return jsonify({'success': False,
                                'message': 'No available drivers without time conflicts for the requested time period'})

            driver = available_drivers

            if vehicle and driver:
                conn.execute('''
                    UPDATE trip_requests 
                    SET current_status = 'assigned', 
                        assigned_vid = ?,
                        assigned_eid = ?,
                        rejection_reason = NULL
                    WHERE rid = ?
                ''', (vehicle['vid'], driver['eid'], request_id))

                # 更新车辆状态
                conn.execute(
                    "UPDATE vehicles SET vstatus = 'assigned' WHERE vid = ?",
                    (vehicle['vid'],)
                )
            else:
                return jsonify({'success': False, 'message': 'No available vehicles or drivers'})

        elif action == 'reject':
            conn.execute('''
                UPDATE trip_requests 
                SET current_status = 'rejected',
                    rejection_reason = ?
                WHERE rid = ?
            ''', (reject_reason, request_id))

        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': 'Request processed successfully'})
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({'success': False, 'message': f'Processing failed: {str(e)}'})


# 司机仪表板
@app.route('/driver/dashboard')
def driver_dashboard():
    if 'user_id' not in session or session['user_type'] != 'driver':
        return redirect(url_for('index'))

    conn = get_db_connection()

    # 获取司机的员工ID
    user_info = conn.execute(
        'SELECT eid FROM users WHERE uid = ?', (session['user_id'],)
    ).fetchone()

    assigned_trips = conn.execute('''
        SELECT tr.*, e.fname, e.lname, v.plate, v.brand, v.model
        FROM trip_requests tr 
        JOIN employees e ON tr.eid = e.eid 
        JOIN vehicles v ON tr.assigned_vid = v.vid
        WHERE tr.assigned_eid = ? AND tr.current_status IN ('assigned', 'in_progress', 'completed')
        ORDER BY tr.start_time DESC
    ''', (user_info['eid'],)).fetchall()

    # 转换为字典列表并添加时间冲突信息
    trips_list = []
    for trip in assigned_trips:
        trip_dict = dict(trip)

        # 检查时间冲突
        has_conflict = False
        if trip_dict['current_status'] in ['assigned', 'in_progress']:
            for other_trip in assigned_trips:
                if (other_trip['rid'] != trip_dict['rid'] and
                        other_trip['current_status'] in ['assigned', 'in_progress'] and
                        trip_dict['start_time'] <= other_trip['end_time'] and
                        trip_dict['end_time'] >= other_trip['start_time']):
                    has_conflict = True
                    break

        trip_dict['has_conflict'] = has_conflict
        trips_list.append(trip_dict)

    conn.close()

    # 计算当前行程数量
    current_trips_count = len(
        [trip for trip in trips_list if trip['current_status'] in ['assigned', 'in_progress']])

    # 传递 datetime 模块到模板
    return render_template('driver_dashboard.html',
                           trips=trips_list,
                           current_trips_count=current_trips_count,
                           datetime=datetime)


# 更新行程状态
@app.route('/driver/update_trip_status', methods=['POST'])
def update_trip_status():
    if 'user_id' not in session or session['user_type'] != 'driver':
        return jsonify({'success': False, 'message': 'Unauthorized access'})

    data = request.json
    trip_id = data['trip_id']
    status = data['status']
    current_mileage = data.get('current_mileage')
    fuel = data.get('fuel')  # 使用fuel而不是current_fuel

    conn = get_db_connection()

    try:
        # 获取行程信息，包括分配的车辆ID
        trip = conn.execute(
            'SELECT assigned_vid FROM trip_requests WHERE rid = ?',
            (trip_id,)
        ).fetchone()

        if not trip:
            return jsonify({'success': False, 'message': 'Trip not found'})

        # 更新行程状态
        conn.execute(
            'UPDATE trip_requests SET current_status = ? WHERE rid = ?',
            (status, trip_id)
        )

        # 如果状态变为"completed"，更新车辆状态和记录车辆信息
        if status == 'completed' and trip['assigned_vid']:
            # 更新车辆状态为"available"
            conn.execute(
                "UPDATE vehicles SET vstatus = 'available' WHERE vid = ?",
                (trip['assigned_vid'],)
            )

            # 如果提供了车辆信息，更新车辆详情
            if current_mileage is not None:
                conn.execute(
                    "UPDATE vehicles SET current_mileage = ? WHERE vid = ?",
                    (current_mileage, trip['assigned_vid'])
                )

            if fuel is not None:
                # 确保fuel是合适的DECIMAL值
                try:
                    fuel_value = float(fuel)
                    if 0 <= fuel_value <= 100:
                        conn.execute(
                            "UPDATE vehicles SET fuel = ? WHERE vid = ?",
                            (fuel_value, trip['assigned_vid'])
                        )
                    else:
                        return jsonify({'success': False, 'message': 'Fuel level must be between 0 and 100.'})
                except ValueError:
                    return jsonify({'success': False, 'message': 'Invalid fuel value.'})

            # 可选：记录行程结束时间和车辆使用信息到单独的表中
            # 这里可以根据需要扩展，比如创建一个trip_completion_records表

        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': 'Trip status updated successfully'})
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({'success': False, 'message': f'Update failed: {str(e)}'})


# 数据库管理员仪表板
@app.route('/admin/dashboard')
def admin_dashboard():
    if 'user_id' not in session or session['user_type'] != 'database_manager':
        return redirect(url_for('index'))

    table = request.args.get('table', 'users')
    conn = get_db_connection()

    try:
        # 获取表数据
        data = conn.execute(f'SELECT * FROM {table}').fetchall()

        # 获取所有表名
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()

        # 获取列名
        columns = []
        if data:
            columns = data[0].keys()

        conn.close()

        return render_template('admin_dashboard.html',
                               data=data,
                               tables=[t['name'] for t in tables],
                               current_table=table,
                               columns=columns)
    except Exception as e:
        conn.close()
        return render_template('admin_dashboard.html',
                               data=[],
                               tables=[],
                               current_table=table,
                               columns=[],
                               error=str(e))


# 管理员执行SQL
@app.route('/admin/execute_sql', methods=['POST'])
def execute_sql():
    if 'user_id' not in session or session['user_type'] != 'database_manager':
        return jsonify({'success': False, 'message': 'Unauthorized access'})

    data = request.json
    sql = data['sql']

    conn = get_db_connection()

    try:
        if sql.strip().lower().startswith('select'):
            result = conn.execute(sql).fetchall()
            columns = [description[0] for description in conn.description] if conn.description else []
            conn.close()
            return jsonify({
                'success': True,
                'data': [dict(row) for row in result],
                'columns': columns
            })
        else:
            # 执行非SELECT语句
            conn.execute(sql)
            conn.commit()
            conn.close()
            return jsonify({'success': True, 'message': 'SQL executed successfully'})
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'message': f'SQL execution failed: {str(e)}'})


# 管理员数据操作 - 添加记录
@app.route('/admin/add_record', methods=['POST'])
def add_record():
    if 'user_id' not in session or session['user_type'] != 'database_manager':
        return jsonify({'success': False, 'message': 'Unauthorized access'})

    data = request.json
    table = data['table']
    record_data = data['data']

    conn = get_db_connection()

    try:
        columns = ', '.join(record_data.keys())
        placeholders = ', '.join(['?' for _ in record_data])
        values = list(record_data.values())

        sql = f'INSERT INTO {table} ({columns}) VALUES ({placeholders})'
        conn.execute(sql, values)
        conn.commit()
        conn.close()

        return jsonify({'success': True, 'message': 'Record added successfully'})
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'message': f'Failed to add record: {str(e)}'})


# 管理员数据操作 - 更新记录
@app.route('/admin/update_record', methods=['POST'])
def update_record():
    if 'user_id' not in session or session['user_type'] != 'database_manager':
        return jsonify({'success': False, 'message': 'Unauthorized access'})

    data = request.json
    table = data['table']
    record_id = data['id']
    record_data = data['data']
    id_column = data.get('id_column', 'id')  # 默认使用'id'作为主键列名

    conn = get_db_connection()

    try:
        set_clause = ', '.join([f'{key} = ?' for key in record_data.keys()])
        values = list(record_data.values())
        values.append(record_id)

        sql = f'UPDATE {table} SET {set_clause} WHERE {id_column} = ?'
        conn.execute(sql, values)
        conn.commit()
        conn.close()

        return jsonify({'success': True, 'message': 'Record updated successfully'})
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'message': f'Failed to update record: {str(e)}'})


# 管理员数据操作 - 删除记录
@app.route('/admin/delete_record', methods=['POST'])
def delete_record():
    if 'user_id' not in session or session['user_type'] != 'database_manager':
        return jsonify({'success': False, 'message': 'Unauthorized access'})

    data = request.json
    table = data['table']
    record_id = data['id']
    id_column = data.get('id_column', 'id')  # 默认使用'id'作为主键列名

    conn = get_db_connection()

    try:
        sql = f'DELETE FROM {table} WHERE {id_column} = ?'
        conn.execute(sql, (record_id,))
        conn.commit()
        conn.close()

        return jsonify({'success': True, 'message': 'Record deleted successfully'})
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'message': f'Failed to delete record: {str(e)}'})


# 用户取消用车申请
@app.route('/user/cancel_request', methods=['POST'])
def cancel_request():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'})

    data = request.json
    request_id = data.get('request_id')

    conn = get_db_connection()
    try:
        # 1. 检查申请当前的状态
        cur = conn.execute('SELECT current_status FROM trip_requests WHERE rid = ?', (request_id,))
        row = cur.fetchone()

        if not row:
            return jsonify({'success': False, 'message': 'Request not found'})

        current_status = row['current_status']

        # 2. 只有特定状态可以取消 (Pending, Approved, Assigned)
        allowed_statuses = ['pending', 'approved', 'assigned']

        if current_status.lower() not in allowed_statuses:
            return jsonify({'success': False, 'message': f'Cannot cancel request in "{current_status}" status'})

        # 3. 执行更新
        conn.execute("UPDATE trip_requests SET current_status = 'cancelled' WHERE rid = ?", (request_id,))
        conn.commit()

        return jsonify({'success': True, 'message': 'Request cancelled successfully'})

    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': str(e)})
    finally:
        conn.close()


# 注册页面
@app.route('/register')
def register_page():
    return render_template('register.html')


# 检查员工ID是否有效
@app.route('/check_employee', methods=['POST'])
def check_employee():
    data = request.json
    eid = data.get('eid')

    conn = get_db_connection()
    employee = conn.execute('''
        SELECT e.*, d.dname 
        FROM employees e 
        JOIN departments d ON e.did = d.did 
        WHERE e.eid = ? AND e.e_is_active = 1
    ''', (eid,)).fetchone()
    conn.close()

    if employee:
        # 根据员工角色映射用户类型
        role_to_utype = {
            'employee': 'normal',
            'manager': 'normal',
            'driver': 'driver',
            'approver': 'approver',
            'database_manager': 'database_manager'
        }
        user_type = role_to_utype.get(employee['role'], 'normal')

        return jsonify({
            'exists': True,
            'employee': dict(employee),
            'user_type': user_type
        })
    else:
        return jsonify({'exists': False})


# 处理注册
@app.route('/register', methods=['POST'])
def register():
    eid = request.form['eid']
    username = request.form['username']
    password = request.form['password']

    conn = get_db_connection()

    try:
        # 验证员工ID是否存在且活跃
        employee = conn.execute('''
            SELECT * FROM employees 
            WHERE eid = ? AND e_is_active = 1
        ''', (eid,)).fetchone()

        if not employee:
            return render_template('register.html',
                                   error='Invalid employee ID or employee is not active')

        # 检查用户名是否已存在
        existing_user = conn.execute(
            'SELECT uid FROM users WHERE username = ?',
            (username,)
        ).fetchone()

        if existing_user:
            return render_template('register.html',
                                   error='Username already exists')

        # 根据员工角色确定用户类型
        role_to_utype = {
            'employee': 'normal',
            'manager': 'normal',
            'driver': 'driver',
            'approver': 'approver',
            'database_manager': 'database_manager'
        }
        user_type = role_to_utype.get(employee['role'], 'normal')

        # 插入新用户并获取生成的UID
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO users (username, password, eid, utype)
            VALUES (?, ?, ?, ?)
        ''', (username, password, eid, user_type))

        # 获取新创建用户的UID
        new_uid = cursor.lastrowid

        conn.commit()
        conn.close()

        return render_template('register.html',
                               success=f'Account created successfully! Your User ID is: {new_uid}. You can now login with this ID.')

    except Exception as e:
        conn.rollback()
        conn.close()
        return render_template('register.html',
                               error=f'Registration failed: {str(e)}')


# 注销
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))


if __name__ == '__main__':
    app.run(debug=True, port=5000)