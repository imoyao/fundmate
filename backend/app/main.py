# app/main.py
from apiflask import APIFlask


def create_app():
    app = APIFlask(__name__)

    # 一个简单的健康检查接口，验证框架是否正常
    @app.get('/api/health')
    def health_check():
        return {'status': 'ok', 'message': 'FundMate V2 is running'}

    return app


app = create_app()

if __name__ == '__main__':
    app.run(debug=True)
