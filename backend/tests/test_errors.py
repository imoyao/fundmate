from backend.fundmate.errors import StatusCodeError


class TestStatusCode:

    def setup_class(self):
        """
        验证类由两个部分组成
        :return:
        """
        self.list_of_status_code_enum = list(StatusCodeError)
        self.enum_len = len(self.list_of_status_code_enum)
        for enum_item in self.list_of_status_code_enum:
            status_code_item = enum_item.value
            assert len(status_code_item) == 2

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
