from backend.fundmate.data.sipf.confidence import Confidence


# FIXME: 更多测试用例

class TestConfidence:
    def setup_class(self):
        self.confidence = Confidence()

    def test_full_chart_data(self):
        result = self.confidence.full_chart_data()
        assert result
        assert isinstance(result, dict)

    def test_detail_of_month(self):
        result = self.confidence.detail_of_month()
        assert result
        assert isinstance(result, dict)
