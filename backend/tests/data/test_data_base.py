from backend.fundmate.data.base import SB1


class TestSB1:
    def setup_class(self):
        """
        类开始时，实例化类
        :return:
        """
        self.sb = SB1()

    def test_detail(self):
        assert self.sb
        self.sb.detail('1234345')
