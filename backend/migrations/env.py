from __future__ import with_statement

import logging
from logging.config import fileConfig

from flask import current_app

from alembic import context

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config
CUSTOM_APP_PREFIX = 'backend.'

# Interpret the config file for Python logging.
# This line sets up loggers basically.
fileConfig(config.config_file_name)
logger = logging.getLogger('alembic.env')

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
config.set_main_option('sqlalchemy.url', str(current_app.extensions['migrate'].db.get_engine().url).replace('%', '%%'))
target_metadata = current_app.extensions['migrate'].db.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline():
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """

    # this callback is used to prevent an auto-migration from being generated
    # when there are no changes to the schema
    # reference: http://alembic.zzzcomputing.com/en/latest/cookbook.html
    def process_revision_directives(context, revision, directives):
        if getattr(config.cmd_opts, 'autogenerate', False):
            script = directives[0]
            if script.upgrade_ops.is_empty():
                directives[:] = []
                logger.info('No changes in schema detected.')

    connectable = current_app.extensions['migrate'].db.get_engine()

    with connectable.connect() as connection:
        context.configure(connection=connection,
                          target_metadata=target_metadata,
                          process_revision_directives=process_revision_directives,
                          render_item=render_item,
                          **current_app.extensions['migrate'].configure_args)

        with context.begin_transaction():
            context.run_migrations()


def render_item(type_, obj, autogen_context):
    """Apply custom rendering for selected items.
    see also: https://stackoverflow.com/a/61320562/14295718
    """
    if type_ == "type":
        module_name = obj.__class__.__module__
        if module_name.startswith(CUSTOM_APP_PREFIX):
            return render_sqlalchemy_choices_type(obj, autogen_context)

    # default rendering for other objects
    return False


def render_sqlalchemy_choices_type(obj, autogen_context):
    class_name = obj.__class__.__name__
    import_statement = f"from backend.fundmate.database import {class_name}"
    autogen_context.imports.add(import_statement)
    if class_name in ['ChoiceType', 'IntChoiceType']:
        return render_choice_type(obj, autogen_context)
    return f"{class_name}()"


def render_choice_type(obj, autogen_context):
    choices = obj.choices
    if obj.type_impl.__class__.__name__ in ['EnumTypeImpl', 'DkEnumTypeImpl']:
        choices = obj.type_impl.enum_class.__name__
        import_statement = f"from backend.migrations.choices import {choices}"
        autogen_context.imports.add(import_statement)
    return f"{obj.__class__.__name__}(choices={choices})"


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
