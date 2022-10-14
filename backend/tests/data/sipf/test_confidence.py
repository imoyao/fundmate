import pendulum

from backend.fundmate.data.sipf.confidence import Confidence
from backend.fundmate.utils import first_day_of_previous_n_months, today


class TestConfidence:
    def setup_class(self):
        self.confidence = Confidence()

    def test_full_chart_data(self):
        result = self.confidence.full_chart_data()
        assert result
        assert isinstance(result, dict)

    def test_detail_of_month(self):
        today_date_str = today()
        today_date = pendulum.parse(today_date_str)
        year, month = today_date.year, today_date.month
        previous_2_months = first_day_of_previous_n_months(is_strict=False, months=4)
        p_date = pendulum.parse(previous_2_months)
        p_year, p_month = p_date.year, p_date.month
        result = self.confidence.detail_of_month(year=year, month=month)
        p_result = self.confidence.detail_of_month(year=p_year, month=p_month)
        assert p_result
        assert isinstance(p_result, dict)
        assert not result
