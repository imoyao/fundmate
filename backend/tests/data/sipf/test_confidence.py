import pytest

from backend.fundmate.data.sipf.confidence import Confidence


class TestConfidence:
    def setup_class(self):
        self.confidence = Confidence()

    def test_full_chart_data(self):
        result = self.confidence.full_chart_data()
        assert result
        assert isinstance(result, dict)

    @pytest.mark.parametrize('year,month', [
        (2022, 1),
        (None, None),
    ])
    def test_detail_of_month(self, year, month):
        result = self.confidence.detail_of_month(year=year, month=month)
        if all([year, month]):
            assert result
            assert isinstance(result, dict)
        else:
            assert not result

    def test_latest_info(self):
        result = self.confidence.latest_info()
        assert result
        assert isinstance(result, dict)
