from flask import Blueprint, jsonify, request, session
from models.user import user_model
from utils.decorators import admin_required, sponsor_required, current_user

admin_bp = Blueprint('admin_api', __name__, url_prefix='/api/admin')

# ── Users ─────────────────────────────────────────────────────────────────

@admin_bp.route('/users', methods=['GET'])
@admin_required
def list_users():
    search = request.args.get('q','').strip()
    role   = request.args.get('role','').strip() or None
    users  = user_model.all_users(search=search or None, role=role)
    return jsonify({'ok': True, 'users': users})

@admin_bp.route('/users', methods=['POST'])
@admin_required
def create_user():
    d = request.get_json() or {}
    ok, result = user_model.create_user(
        d.get('username',''), d.get('password',''),
        d.get('email',''), d.get('role','user'))
    if not ok:
        return jsonify({'ok': False, 'error': result}), 400
    return jsonify({'ok': True, 'user': result})

@admin_bp.route('/users/<username>', methods=['PUT'])
@admin_required
def update_user(username):
    d = request.get_json() or {}
    ok, msg = user_model.update_user(username, d)
    if not ok:
        return jsonify({'ok': False, 'error': msg}), 400
    return jsonify({'ok': True, 'message': msg})

@admin_bp.route('/users/<username>', methods=['DELETE'])
@admin_required
def delete_user(username):
    if not user_model.delete_user(username):
        return jsonify({'ok': False, 'error': 'Cannot delete user'}), 400
    return jsonify({'ok': True})

@admin_bp.route('/users/<username>/suspend', methods=['POST'])
@admin_required
def suspend_user(username):
    d = request.get_json() or {}
    suspend = d.get('suspend', True)
    ok, msg = user_model.suspend_user(username, suspend)
    if not ok:
        return jsonify({'ok': False, 'error': msg}), 400
    return jsonify({'ok': True, 'message': msg})

# Legacy endpoint used by old admin.html
@admin_bp.route('/delete', methods=['POST'])
@admin_required
def delete_user_legacy():
    d = request.get_json() or {}
    username = d.get('username','').strip()
    if not username:
        return jsonify({'ok': False, 'error': 'Username required'}), 400
    if not user_model.delete_user(username):
        return jsonify({'ok': False, 'error': 'User not found or cannot be deleted'}), 404
    return jsonify({'ok': True})

# ── Bundles ───────────────────────────────────────────────────────────────

@admin_bp.route('/bundles', methods=['GET'])
@admin_required
def list_bundles():
    from models.db import get_conn
    org_id = user_model.get_user(session['username'])['org_id']
    bundles = user_model.get_bundles(org_id)
    return jsonify({'ok': True, 'bundles': bundles})

@admin_bp.route('/bundles', methods=['POST'])
@admin_required
def create_bundle():
    d = request.get_json() or {}
    me = user_model.get_user(session['username'])
    bundle = user_model.create_bundle(
        name=d.get('name','Unnamed Bundle'),
        depth=d.get('depth', 3),
        game_count=d.get('game_count', 5),
        created_by=me['id'],
        org_id=me['org_id'],
        description=d.get('description',''))
    return jsonify({'ok': True, 'bundle': bundle})

@admin_bp.route('/bundles/<bundle_id>', methods=['PUT'])
@admin_required
def update_bundle(bundle_id):
    d = request.get_json() or {}
    ok, msg = user_model.update_bundle(bundle_id, d)
    if not ok:
        return jsonify({'ok': False, 'error': msg}), 400
    return jsonify({'ok': True})

@admin_bp.route('/bundles/<bundle_id>', methods=['DELETE'])
@admin_required
def delete_bundle(bundle_id):
    user_model.delete_bundle(bundle_id)
    return jsonify({'ok': True})

@admin_bp.route('/bundles/<bundle_id>/assign', methods=['POST'])
@admin_required
def assign_bundle(bundle_id):
    d = request.get_json() or {}
    me = user_model.get_user(session['username'])
    ok, msg = user_model.assign_bundle(bundle_id, d.get('username',''), me['id'])
    if not ok:
        return jsonify({'ok': False, 'error': msg}), 400
    return jsonify({'ok': True})

# ── Invites ───────────────────────────────────────────────────────────────

@admin_bp.route('/invites', methods=['GET'])
@admin_required
def list_invites():
    me = user_model.get_user(session['username'])
    invites = user_model.list_invites(org_id=me['org_id'])
    return jsonify({'ok': True, 'invites': invites})

@admin_bp.route('/invites', methods=['POST'])
@admin_required
def create_invite():
    d = request.get_json() or {}
    me = user_model.get_user(session['username'])
    token = user_model.create_invite(
        email=d.get('email',''),
        invited_by_id=me['id'],
        org_id=me['org_id'],
        role=d.get('role','user'),
        bundle_id=d.get('bundle_id'))
    return jsonify({'ok': True, 'token': token,
                    'invite_url': f"/register?invite={token}"})
