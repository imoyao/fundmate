# -*- coding: utf-8 -*-
# Auther : imoyao
# Date : 2023/1/12 22:02
# File : test_collection_models.py
import random

import pytest
from factories import CollectionFactory, LabelOfCollectionFactory, UserFactory

from backend.fundmate.collection.models import Collection, LabelsOfCollection
from backend.fundmate.settings import SupportCollectionsEnum
from backend.fundmate.user.models import User


@pytest.fixture(scope='function')
def random_col_type():
    _col_type = random.choice(list(SupportCollectionsEnum))
    return _col_type


class TestCollection:

    def test_factory(self, random_col_type):
        col = CollectionFactory(collection_type=random_col_type)
        assert col.identify.isdigit()
        assert isinstance(col.creator_id, int)
        assert col.collection_type in list(SupportCollectionsEnum)

    def test_check_has_collected(self, random_col_type):
        user = UserFactory()
        user_inst = User.lookup(user.username)
        user_id = user_inst.id
        assert user_id
        collect = CollectionFactory(creator_id=user_id, collection_type=random_col_type)
        _identify = collect.identify
        rv = Collection.get_collection(creator_id=user_id, collection_type=random_col_type, identify=_identify)
        assert rv
        assert rv.collection_type in list(SupportCollectionsEnum)


class TestLabelsOfCollection:
    def test_factory(self):
        label = LabelOfCollectionFactory()
        assert label.name
        assert label.color.startswith('#')
        with_emoji_label = LabelOfCollectionFactory(name='🤩YYDS')
        assert with_emoji_label.name

    def test_has_same_label_name_by_user(self):
        label = LabelOfCollectionFactory()
        new_name = label.name
        user_id = label.creator_id
        has_created = LabelsOfCollection.has_same_label_name_by_user(user_id, new_name)
        assert has_created
        new_user_id = user_id + 1
        has_created = LabelsOfCollection.has_same_label_name_by_user(new_user_id, new_name)
        assert not has_created
