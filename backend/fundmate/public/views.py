# -*- coding: utf-8 -*-
"""Public section, including homepage and signup."""
from flask import flash, redirect, request, url_for
from flask.views import MethodView
# from flask_login import login_required, login_user, logout_user
from apiflask import Schema, input, output, abort, APIBlueprint
from apiflask.fields import Integer, String, Boolean, Email
from apiflask.validators import Length, OneOf, Equal
from marshmallow import pre_load, ValidationError
from backend.fundmate.extensions import login_manager
from backend.fundmate.user.models import User
from backend.fundmate.schema_ext import RegisterSchema
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


# class RegisterSchema(Schema):
#     username = String(required=True, validate=Length(5, 25))
#     password = String(required=True, validate=Length(6, 40))
#     re_password = String(required=True, validate=(Length(6, 40), Equal('password')))
#     email = Email(validate=Length(6, 40))
#     is_activated = Boolean()
#     print(password, re_password, '=============')
#
#     # kwargs:[TypeError: pre_load() got an unexpected keyword argument 'many' · Issue #1630 · marshmallow-code/marshmallow](https://github.com/marshmallow-code/marshmallow/issues/1630)
#     @pre_load(pass_many=True)
#     def register_validate(self, data, **kwargs):
#         """Validate the form."""
#         user = User.query.filter_by(username=data.get('username')).first()
#         if user:
#             raise ValidationError("Username already registered")
#         user = User.query.filter_by(email=data.get('email')).first()
#         if user:
#             raise ValidationError("Email already registered")
#         return data


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


pets = [
    {
        'id': 0,
        'name': 'Kitty',
        'category': 'cat'
    },
    {
        'id': 1,
        'name': 'Coco',
        'category': 'dog'
    }
]


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
