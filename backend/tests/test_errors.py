from backend.fundmate.errors import (
    BaseError,
    ClientError,
    CrawlerError,
    LogicConflictError,
    MiddlewareError,
    ServerError,
    ThirdPartError,
    UserInputError,
)


class TestStatusCode:
    def setup_class(self):
        """
        验证类由两个部分组成
        :return:
        """
        self.list_of_status_code_enum = list(BaseError)
        self.enum_len = len(self.list_of_status_code_enum)
        for enum_item in self.list_of_status_code_enum:
            status_code_item = enum_item.value
            assert len(status_code_item) == 2

    @staticmethod
    def base_error(error):
        """
        获取每个类中的基础错误定义
        :param error:
        :return:
        """
        _info = {
            UserInputError: UserInputError.USER_INPUT_ERR,
            ThirdPartError: ThirdPartError.THIRD_PART_ERR,
            CrawlerError: CrawlerError.CRAWLER_ERR,
            ClientError: ClientError.CLIENT_ERR,
            ServerError: ServerError.SERVER_ERR,
            MiddlewareError: MiddlewareError.MIDDLEWARE_ERR,
            LogicConflictError: LogicConflictError.LOGIC_CONFLICT_ERR,
        }
        return _info.get(error)

    def test_status_code(self):
        status_code_set = set()
        for enum_item in self.list_of_status_code_enum:
            status_item_code = enum_item.value[0]
            status_code_set.add(status_item_code)
            assert isinstance(status_item_code, int)
        assert len(status_code_set) == self.enum_len

    def test_message(self):
        for enum_item in self.list_of_status_code_enum:
            status_code_item = enum_item.value
            assert isinstance(status_code_item[1], str)

    def test_error_code_except(self):
        """
        测试每个类下面的状态码都小于基础定义
        :return:
        """
        for error_class in [
            UserInputError,
            ThirdPartError,
            CrawlerError,
            ClientError,
            ServerError,
            MiddlewareError,
            LogicConflictError,
        ]:
            for item in error_class:
                base_error_item = self.base_error(error_class)
                assert item.code >= base_error_item.code
