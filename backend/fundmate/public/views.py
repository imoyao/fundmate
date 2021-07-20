# -*- coding: utf-8 -*-
"""Public section, including homepage and signup."""
from apiflask import APIBlueprint, Schema, abort, input, output
from apiflask.fields import Integer, String
from apiflask.validators import Length, OneOf
from flask import flash, redirect, request, url_for
from flask.views import MethodView

from backend.fundmate import excepts as dt_except
from backend.fundmate.data import danjuan, jsl, yzyx
from backend.fundmate.extensions import login_manager
from backend.fundmate.schema_ext import RegisterSchema
from backend.fundmate.user.models import User

bp = APIBlueprint("public", __name__)


@login_manager.user_loader
def load_user(user_id):
    """Load user by ID."""
    return User.get_by_id(int(user_id))


@bp.route('/')
class Home(MethodView):

    def post(self):
        flash("You are logged in.", "success")
        redirect_url = request.args.get("next") or url_for("user.members")
        return redirect(redirect_url)

    def get(self):
        return {'message': 'Hello,Flask!'}


@bp.route('/register/')
class Register(MethodView):

    @input(RegisterSchema(partial=True))
    def post(self, data):
        User.create(
            username=data.username,
            email=data.email,
            password=data.password,
            active=True,
        )


class PetInSchema(Schema):
    name = String(required=True, validate=Length(0, 10))
    category = String(required=True, validate=OneOf(['dog', 'cat']))


class PetOutSchema(Schema):
    id = Integer()
    name = String()
    category = String()


pets = [{
    'id': 0,
    'name': 'Kitty',
    'category': 'cat'
}, {
    'id': 1,
    'name': 'Coco',
    'category': 'dog'
}]


@bp.route('/pets/<int:pet_id>')
class Pet(MethodView):

    @output(PetOutSchema)
    def get(self, pet_id):
        """Get a pet"""
        if pet_id > len(pets) - 1:
            abort(404)
        return pets[pet_id]

    @input(PetInSchema(partial=True))
    @output(PetOutSchema)
    def patch(self, pet_id, data):
        """Update a pet"""
        if pet_id > len(pets) - 1:
            abort(404)
        for attr, value in data.items():
            pets[pet_id][attr] = value
        return pets[pet_id]


@bp.route("/logout/")
# @login_required
def logout():
    """Logout."""
    # logout_user()
    flash("You are logged out.", "info")
    return redirect(url_for("public.home"))


@bp.route("/about/")
def about():
    """About page."""
    return 'render_template("public/about.html")'


@bp.get('/thermometers')
def thermometer():
    """
    行情估值信息
    目前包括集思录温度、有知有行温度、蛋卷估值
    :return:
    """
    try:
        yzyx_info = yzyx.yzyx.last()
    except dt_except.CrawlerException:
        yzyx_info = None
    jsl_info = jsl.jsl.overview()
    dj_info = danjuan.dj.overview()
    info = {'yzyx': yzyx_info, 'jsl': jsl_info, 'dj': dj_info}
    return info
