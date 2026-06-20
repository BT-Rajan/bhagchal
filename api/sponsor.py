from flask import Blueprint, jsonify, request, session
from models.user import user_model
from utils.decorators import sponsor_required

sponsor_bp = Blueprint('sponsor_api', __name__, url_prefix='/api/sponsor')

@sponsor_bp.route('/bundles', methods=['GET'])
@sponsor_required
def list_bundles():
    me = user_model.get_user(session['username'])
    bundles = user_model.get_bundles(me['org_id'])
    return jsonify({'ok': True, 'bundles': bundles})

@sponsor_bp.route('/bundles', methods=['POST'])
@sponsor_required
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

@sponsor_bp.route('/bundles/<bundle_id>', methods=['PUT'])
@sponsor_required
def update_bundle(bundle_id):
    d = request.get_json() or {}
    # sponsors can only update depth/name on their own bundles
    from models.db import get_conn
    row = get_conn().execute('SELECT created_by FROM game_bundles WHERE id=?',(bundle_id,)).fetchone()
    if not row:
        return jsonify({'ok': False, 'error': 'Bundle not found'}), 404
    me = user_model.get_user(session['username'])
    if me['role'] != 'admin' and row['created_by'] != me['id']:
        return jsonify({'ok': False, 'error': 'Not your bundle'}), 403
    ok, msg = user_model.update_bundle(bundle_id, d)
    return jsonify({'ok': ok, 'error': msg if not ok else None})

@sponsor_bp.route('/bundles/<bundle_id>/assign', methods=['POST'])
@sponsor_required
def assign_bundle(bundle_id):
    d = request.get_json() or {}
    me = user_model.get_user(session['username'])
    ok, msg = user_model.assign_bundle(bundle_id, d.get('username',''), me['id'])
    if not ok:
        return jsonify({'ok': False, 'error': msg}), 400
    return jsonify({'ok': True})

@sponsor_bp.route('/invites', methods=['GET'])
@sponsor_required
def list_invites():
    me = user_model.get_user(session['username'])
    invites = user_model.list_invites(invited_by_id=me['id'])
    return jsonify({'ok': True, 'invites': invites})

@sponsor_bp.route('/invites', methods=['POST'])
@sponsor_required
def create_invite():
    d = request.get_json() or {}
    me = user_model.get_user(session['username'])
    token = user_model.create_invite(
        email=d.get('email',''),
        invited_by_id=me['id'],
        org_id=me['org_id'],
        role='user',
        bundle_id=d.get('bundle_id'))
    return jsonify({'ok': True, 'token': token,
                    'invite_url': f"/register?invite={token}"})

@sponsor_bp.route('/users', methods=['GET'])
@sponsor_required
def list_users():
    me = user_model.get_user(session['username'])
    users = user_model.all_users(org_id=me['org_id'], role='user',
                                 search=request.args.get('q') or None)
    return jsonify({'ok': True, 'users': users})

@sponsor_bp.route('/reports', methods=['GET'])
@sponsor_required
def reports():
    from models.db import get_conn
    me = user_model.get_user(session['username'])
    rows = get_conn().execute(
        '''SELECT g.id,g.human_role,g.difficulty,g.ai_depth,g.status,
                  g.duration_sec,g.created_at,u.username
           FROM games g JOIN users u ON g.user_id=u.id
           WHERE g.org_id=?
           ORDER BY g.created_at DESC LIMIT 200''',
        (me['org_id'],)).fetchall()
    return jsonify({'ok': True, 'games': [dict(r) for r in rows]})
