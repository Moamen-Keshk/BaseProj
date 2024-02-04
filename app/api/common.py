from flask import render_template, redirect, url_for, g, abort, flash, request,\
    current_app, make_response, jsonify
from flask_sqlalchemy.record_queries import get_recorded_queries
from . import api
from .forms import EditProfileAdminForm
from .email import send_email
from .. import db
from .models import Permission, Role, User, Post, Comment, Notification, Agent,\
    Tariff, DocumentType, ServiceType, Embassy, ServiceOption, CollectionType,\
    TariffAssist, Order
from .decorators import admin_required, permission_required
from app.auth.views import basic_auth, token_auth
from .constants import Constants


@api.after_app_request
def after_request(response):
    for query in get_recorded_queries():
        if query.duration >= current_app.config['FLASKY_SLOW_DB_QUERY_TIME']:
            current_app.logger.warning(
                'Slow query: %s\nParameters: %s\nDuration: %fs\nContext: %s\n'
                % (query.statement, query.parameters, query.duration,
                   query.context))
    return response


@api.route('/shutdown')
def server_shutdown():
    if not current_app.testing:
        abort(404)
    shutdown = request.environ.get('werkzeug.server.shutdown')
    if not shutdown:
        abort(500)
    shutdown()
    return 'Shutting down...'


@api.route('/', methods=['GET', 'POST'])
@token_auth.login_required
def index():
    resp = token_auth.current_user()
    if not isinstance(resp, str):
        user = User.query.get_or_404(resp)
        if user.can(Permission.WRITE) and request.method == 'POST':
            post_data = request.get_json()
            post = Post(body=post_data.body.data,author=user)
            db.session.add(post)
            db.session.commit()
            return redirect(url_for('.user_api'))
        page = request.args.get('page', 1, type=int)
        show_followed = False
        if user.is_authenticated:
            show_followed = bool(request.cookies.get('show_followed', ''))
        if show_followed:
            query = user.followed_posts
        else:
            query = Post.query
        pagination = query.order_by(Post.timestamp.desc()).paginate(
            page=page, per_page=current_app.config['FLASKY_POSTS_PER_PAGE'],
            error_out=False)
        posts = pagination.items
        responseObject = {
            'status': 'success',
            'data': {
                'is_authenticated': user.is_authenticated,
                'confirmed': user.confirmed,
                'id': user.id,
                'username': user.username,
                'can_moderate': user.can(Permission.MODERATE),
                'can_write': user.can(Permission.WRITE),
                'avatar_hash': user.gravatar(size=18),
                'posts': posts,
                'show_followed': show_followed
            }
        }
        return make_response(jsonify(responseObject)), 200
    responseObject = {
        'status': 'fail',
        'message': resp
    }
    return make_response(jsonify(responseObject)), 401


@api.route('/avatar')
@token_auth.login_required
def avatar():
    resp = token_auth.current_user()
    if not isinstance(resp, str):
        user = User.query.get_or_404(resp)
        responseObject = {
            'status': 'success',
            'data': user.gravatar(size=18)
        }
        return make_response(jsonify(responseObject)), 200
    responseObject = {
        'status': 'fail',
        'message': resp
    }
    return make_response(jsonify(responseObject)), 401


@api.route('/notifs-count')
@token_auth.login_required
def notifications_count():
    resp = token_auth.current_user()
    if not isinstance(resp, str):
        responseObject = {
            'status': 'success',
            'data': Notification.query.filter_by(to_user=resp, is_read=False).count()
        }
        return make_response(jsonify(responseObject)), 200
    responseObject = {
        'status': 'fail',
        'message': resp
    }
    return make_response(jsonify(responseObject)), 401


@api.route('/notifications')
@token_auth.login_required
def notifications():
    resp = token_auth.current_user()
    if not isinstance(resp, str):
        notifications_list = Notification.query.filter_by(to_user=resp, is_read=False).order_by(
            Notification.timestamp.desc()).limit(6).all()
        for x in notifications_list:
            notifications_list[notifications_list.index(x)] = x.to_json()
        responseObject = {
            'status': 'success',
            'data': notifications_list,
            'page': 0
        }
        return make_response(jsonify(responseObject)), 200
    responseObject = {
        'status': 'fail',
        'message': resp
    }
    return make_response(jsonify(responseObject)), 401


@api.route('/all-notifications')
@token_auth.login_required
def all_notifications():
    resp = token_auth.current_user()
    if not isinstance(resp, str):
        notifications_list = Notification.query.filter_by(
            to_user=resp, is_read=False).order_by(Notification.timestamp.desc()).all()
        for x in notifications_list:
            notifications_list[notifications_list.index(x)] = x.to_json()
        responseObject = {
            'status': 'success',
            'data': notifications_list,
            'page': 0
        }
        return make_response(jsonify(responseObject)), 200
    responseObject = {
        'status': 'fail',
        'message': resp
    }
    return make_response(jsonify(responseObject)), 401


@api.route('/order-list/<int:status_id>')
@token_auth.login_required
def order_list(status_id):
    resp = token_auth.current_user()
    if not isinstance(resp, str):
        try:
            orders_list = [o.to_json() for o in Order.query.filter_by(
                status_id=status_id).order_by(Order.id.desc()).all()]
            responseObject = {
                'status': 'success',
                'data': orders_list,
                'page': 0
            }
            return make_response(jsonify(responseObject)), 200
        except Exception as e:
            responseObject = {
                'status': 'error',
                'message': 'Some error occurred. Please try again.'
            }
            return make_response(jsonify(responseObject)), 401
    responseObject = {
        'status': 'fail',
        'message': resp
    }
    return make_response(jsonify(responseObject)), 401


@api.route('/order-detail/<int:order_id>')
@token_auth.login_required
def order_detail(order_id):
    resp = token_auth.current_user()
    if not isinstance(resp, str):
        try:
            orders_detail = Order.query.get_or_404(order_id).to_full_json()
            responseObject = {
                'status': 'success',
                'data': orders_detail,
                'page': 0
            }
            return make_response(jsonify(responseObject)), 200
        except Exception as e:
            responseObject = {
                'status': 'error',
                'message': 'Some error occurred. Please try again.'
            }
            return make_response(jsonify(responseObject)), 401
    responseObject = {
        'status': 'fail',
        'message': resp
    }
    return make_response(jsonify(responseObject)), 401


@api.route('/advance-orders', methods=['GET', 'POST'])
@token_auth.login_required
def advance_orders():
    resp = token_auth.current_user()
    if not isinstance(resp, str):
        try:
            orders_list = Order.query.filter(Order.id.in_(request.get_json().get('order_ids'))).all()
            new_status_id = (request.get_json().get('status_id')+1)
            for o in orders_list:
                o.status_id = new_status_id
                db.session.add(o)
            db.session.commit()
            responseObject = {
                'status': 'success',
                'page': 0
            }
            return make_response(jsonify(responseObject)), 200
        except Exception as e:
            responseObject = {
                'status': 'error',
                'message': 'Some error occurred. Please try again.'
            }
            return make_response(jsonify(responseObject)), 401
    responseObject = {
        'status': 'fail',
        'message': resp
    }
    return make_response(jsonify(responseObject)), 401


@api.route('/edit-profile', methods=['GET', 'POST'])
@token_auth.login_required
def edit_profile():
    resp = token_auth.current_user()
    if not isinstance(resp, str):
        user = User.query.get_or_404(resp)
        post_data = request.get_json()
        user.name = post_data.get('name')
        user.location = post_data.get('location')
        user.about_me = post_data.get('about')
        db.session.add(user)
        db.session.commit()
        responseObject = {
            'status': 'success',
            'message': 'Your profile has been updated.'
        }
        return make_response(jsonify(responseObject)), 200
    else:
        responseObject = {
            'status': 'fail',
            'message': 'Session expired, log in required!'
        }
        return make_response(jsonify(responseObject)), 202


@api.route('/edit-tariff', methods=['GET', 'POST'])
@token_auth.login_required
def edit_tariff():
    resp = token_auth.current_user()
    if not isinstance(resp, str):
        post_data = request.get_json()
        trf = Tariff.query.get(post_data.get('id'))
        trf.std_w = post_data.get('standard_w')
        trf.exp_w = post_data.get('express_w')
        trf.urg_w = post_data.get('urgent_w')
        trf.std_f = post_data.get('standard_f')
        trf.exp_f = post_data.get('express_f')
        trf.urg_f = post_data.get('urgent_f')
        db.session.add(trf)
        db.session.commit()
        TariffAssist.update_embassy(trf.embassy_id, [post_data.get('standard_w'), post_data.get('express_w'),
                                                     post_data.get('urgent_w'), post_data.get('standard_f'),
                                                     post_data.get('express_f'), post_data.get('urgent_f')])
        responseObject = {
            'status': 'success',
            'message': 'Tariff has been updated.'
        }
        return make_response(jsonify(responseObject)), 200
    else:
        responseObject = {
            'status': 'fail',
            'message': 'Session expired, log in required!'
        }
        return make_response(jsonify(responseObject)), 202


@api.route('/agent-request/<int:agent_id>')
@token_auth.login_required
def agent_request(agent_id):
    resp = token_auth.current_user()
    if not isinstance(resp, str):
        agent_req = Agent.query.get(agent_id).to_json()
        responseObject = {
            'status': 'success',
            'data': agent_req
        }
        return make_response(jsonify(responseObject)), 200
    responseObject = {
        'status': 'fail',
        'message': resp
    }
    return make_response(jsonify(responseObject)), 401


@api.route('/action-agent', methods=['GET', 'POST'])
@token_auth.login_required
def action_agent():
    resp = token_auth.current_user()
    if not isinstance(resp, str):
        post_data = request.get_json()
        agent_req = Agent.query.get(post_data.get('agent_id'))
        notification = Notification.query.get(post_data.get('notification_id'))
        action = post_data.get('action')
        agent_req.status = action
        if action == 'Confirmed':
            send_email(agent_req.email, 'Agent Confirmation',
                       'auth/email/agent_confirmation', user=agent_req)
        notification.is_read = True
        db.session.commit()
        responseObject = {
            'status': 'success'
        }
        return make_response(jsonify(responseObject)), 200
    responseObject = {
        'status': 'fail',
        'message': resp
    }
    return make_response(jsonify(responseObject)), 401


@api.route('/tariff')
@token_auth.login_required
def tariff():
    resp = token_auth.current_user()
    if not isinstance(resp, str):
        trf_list = Tariff.query.order_by(Tariff.embassy_id).all()
        for x in trf_list:
            trf_list[trf_list.index(x)] = x.to_json()
        responseObject = {
            'status': 'success',
            'data': trf_list,
            'page': 0
        }
        return make_response(jsonify(responseObject)), 200
    responseObject = {
        'status': 'fail',
        'message': resp
    }
    return make_response(jsonify(responseObject)), 401


@api.route('/new-order-options')
@token_auth.login_required
def new_order_options():
    resp = token_auth.current_user()
    if not isinstance(resp, str):
        doc_types = [type_name[0] for type_name in DocumentType.query.order_by(
            DocumentType.id).with_entities(DocumentType.name).all()]
        service_types = [type_name[0] for type_name in ServiceType.query.order_by(
            ServiceType.id).with_entities(ServiceType.name).all()]
        embassies = [emb_name[0] for emb_name in Embassy.query.order_by(
            Embassy.id).with_entities(Embassy.name).all()]
        service_options = [opt_name[0] for opt_name in ServiceOption.query.order_by(
            ServiceOption.id).with_entities(ServiceOption.name).all()]
        doc_versions = ['Copy', 'Original']
        collection_types = [type_name[0] for type_name in CollectionType.query.order_by(
            CollectionType.id).with_entities(CollectionType.name).all()]
#        for x in doc_types:
#            doc_types[doc_types.index(x)] = x.to_json()
        responseObject = {
            'status': 'success',
            'doc_types': doc_types,
            'service_types': service_types,
            'embassies': embassies,
            'service_options': service_options,
            'doc_versions': doc_versions,
            'collection_types': collection_types,
            'page': 0
        }
        return make_response(jsonify(responseObject)), 200
    responseObject = {
        'status': 'fail',
        'message': resp
    }
    return make_response(jsonify(responseObject)), 401


@api.route('/edit-profile/<int:id>', methods=['GET', 'POST'])
@basic_auth.login_required
@admin_required
def edit_profile_admin(id):
    user = User.query.get_or_404(id)
    form = EditProfileAdminForm(user=user)
    if form.validate_on_submit():
        user.email = form.email.data
        user.username = form.username.data
        user.confirmed = form.confirmed.data
        user.role = Role.query.get(form.role.data)
        user.name = form.name.data
        user.location = form.location.data
        user.about_me = form.about_me.data
        db.session.add(user)
        db.session.commit()
        flash('The profile has been updated.')
        return redirect(url_for('.get_user', id=user.id))
    form.email.data = user.email
    form.username.data = user.username
    form.confirmed.data = user.confirmed
    form.role.data = user.role_id
    form.name.data = user.name
    form.location.data = user.location
    form.about_me.data = user.about_me
    return render_template('edit_profile.html', form=form, user=user)


@api.route('/follow/<username>')
@basic_auth.login_required
@permission_required(Permission.FOLLOW)
def follow(username):
    user = User.query.filter_by(username=username).first()
    if user is None:
        flash('Invalid user.')
        return redirect(url_for('.index'))
    if g.current_user.is_following(user):
        flash('You are already following this user.')
        return redirect(url_for('.get_user', id=user.id))
    g.current_user.follow(user)
    db.session.commit()
    flash('You are now following %s.' % username)
    return redirect(url_for('.get_user', id=user.id))


@api.route('/unfollow/<username>')
@basic_auth.login_required
@permission_required(Permission.FOLLOW)
def unfollow(username):
    user = User.query.filter_by(username=username).first()
    if user is None:
        flash('Invalid user.')
        return redirect(url_for('.index'))
    if not g.current_user.is_following(user):
        flash('You are not following this user.')
        return redirect(url_for('.get_user', id=user.id))
    g.current_user.unfollow(user)
    db.session.commit()
    flash('You are not following %s anymore.' % username)
    return redirect(url_for('.get_user', id=user.id))


@api.route('/followers/<username>')
def followers(username):
    user = User.query.filter_by(username=username).first()
    if user is None:
        flash('Invalid user.')
        return redirect(url_for('.index'))
    page = request.args.get('page', 1, type=int)
    pagination = user.followers.paginate(
        page=page, per_page=current_app.config['FLASKY_FOLLOWERS_PER_PAGE'],
        error_out=False)
    follows = [{'user': item.follower, 'timestamp': item.timestamp}
               for item in pagination.items]
    return render_template('followers.html', user=user, title="Followers of",
                           endpoint='.followers', pagination=pagination,
                           follows=follows)


@api.route('/followed_by/<username>')
def followed_by(username):
    user = User.query.filter_by(username=username).first()
    if user is None:
        flash('Invalid user.')
        return redirect(url_for('.index'))
    page = request.args.get('page', 1, type=int)
    pagination = user.followed.paginate(
        page=page, per_page=current_app.config['FLASKY_FOLLOWERS_PER_PAGE'],
        error_out=False)
    follows = [{'user': item.followed, 'timestamp': item.timestamp}
               for item in pagination.items]
    return render_template('followers.html', user=user, title="Followed by",
                           endpoint='.followed_by', pagination=pagination,
                           follows=follows)


@api.route('/all')
@basic_auth.login_required
def show_all():
    resp = make_response(redirect(url_for('.index')))
    resp.set_cookie('show_followed', '', max_age=30*24*60*60)
    return jsonify({
        'resp': resp
    })


@api.route('/followed')
@basic_auth.login_required
def show_followed():
    resp = make_response(redirect(url_for('.index')))
    resp.set_cookie('show_followed', '1', max_age=30*24*60*60)
    return jsonify({
        'resp': resp
    })


@api.route('/moderate')
@basic_auth.login_required
@permission_required(Permission.MODERATE)
def moderate():
    page = request.args.get('page', 1, type=int)
    pagination = Comment.query.order_by(Comment.timestamp.desc()).paginate(
        page=page, per_page=current_app.config['FLASKY_COMMENTS_PER_PAGE'],
        error_out=False)
    comments = pagination.items
    return render_template('moderate.html', comments=comments,
                           pagination=pagination, page=page)


@api.route('/moderate/enable/<int:id>')
@basic_auth.login_required
@permission_required(Permission.MODERATE)
def moderate_enable(id):
    comment = Comment.query.get_or_404(id)
    comment.disabled = False
    db.session.add(comment)
    db.session.commit()
    return redirect(url_for('.moderate',
                            page=request.args.get('page', 1, type=int)))


@api.route('/moderate/disable/<int:id>')
@basic_auth.login_required
@permission_required(Permission.MODERATE)
def moderate_disable(id):
    comment = Comment.query.get_or_404(id)
    comment.disabled = True
    db.session.add(comment)
    db.session.commit()
    return redirect(url_for('.moderate',
                            page=request.args.get('page', 1, type=int)))
