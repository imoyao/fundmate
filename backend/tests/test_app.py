import pytest
from apiflask import APIBlueprint

from .schemas import FooSchema


def test_app_init(app):
    assert app
    assert hasattr(app, 'import_name')
    assert hasattr(app, 'title')
    assert 'TAGS' in app.config
    assert 'openapi' in app.blueprints


def test_index(app, client):
    rv = client.get('/')
    assert rv.status_code == 200
    assert rv.headers['Content-Type'] == 'text/html; charset=utf-8'


@pytest.mark.parametrize(
    'numerator,denominator,expected',
    [
        (8, 4, 8 / 4),
        # (8, 0, None)      # FIXME: 如何在测试环境中处理异常状况？
    ],
)
def test_sentry(app, client, numerator, denominator, expected):
    if denominator == 0:
        with pytest.raises(ZeroDivisionError):
            rv = client.get(f'/sentry/{numerator}/divide/{denominator}/')
            assert rv.status_code == 500
            return True

    rv = client.get(f'/sentry/{numerator}/divide/{denominator}/')
    assert rv.status_code == 200
    assert rv.headers['Content-Type'] == 'application/json'
    result = rv.json
    print(result)
    assert 'detail' in result
    aws = result.get('detail').get('answer')
    assert aws == expected


@pytest.mark.skip()
def test_dispatch_static_request(app, client):
    # keyword arguments
    rv = client.get('/static/hello.css')  # endpoint: static
    assert rv.status_code == 404

    # positional arguments
    @app.get('/mystatic/<int:pet_id>')
    @input(FooSchema)
    def mystatic(pet_id, foo):  # endpoint: mystatic
        return {'pet_id': pet_id, 'foo': foo}

    rv = client.get('/mystatic/2', json={'id': 1, 'name': 'foo'})
    assert rv.status_code == 200
    assert rv.json['pet_id'] == 2
    assert rv.json['foo'] == {'id': 1, 'name': 'foo'}

    # positional arguments
    # blueprint static route accepts both keyword/positional arguments
    bp = APIBlueprint('foo', __name__, static_folder='static')
    app.register_blueprint(bp, url_prefix='/foo')
    rv = client.get('/foo/static/hello.css')  # endpoint: foo.static
    assert rv.status_code == 404


def schema_name_resolver1(schema):
    name = schema.__class__.__name__
    if schema.partial:
        name += '_'
    return name


def schema_name_resolver2(schema):
    name = schema.__class__.__name__
    if name.endswith('Schema'):
        name = name[:-6] or name
    if schema.partial:
        name += 'Partial'
    return name
