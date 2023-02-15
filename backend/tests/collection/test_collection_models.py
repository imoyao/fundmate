# -*- coding: utf-8 -*-
# Auther : imoyao
# Date : 2023/1/12 22:02
# File : test_collection_models.py
import random

import pytest
from faker import Faker

from backend.fundmate.collection.models import CategoriesOfCollection, Collection, LabelsOfCollection
from backend.fundmate.excepts import UniqueInstanceError
from backend.fundmate.settings import SupportCollectionsEnum
from backend.fundmate.user.models import User
from backend.tests.collection.collection_teardown import (
    delete_all_categories,
    delete_all_collections,
    delete_all_labels,
    random_collection_type,
)
from backend.tests.factories import (
    CategoryOfCollectionFactory,
    CollectionFactory,
    LabelOfCollectionFactory,
    UserFactory,
)


@pytest.fixture(scope='function')
def random_col_type():
    _col_type = random.choice(list(SupportCollectionsEnum))
    return _col_type


class TestCollection:
    def teardown(self):
        delete_all_collections()

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

    def teardown(self):
        delete_all_labels()

    def test_factory(self):
        label = LabelOfCollectionFactory()
        assert label.name
        assert label.color.startswith('#')
        with_emoji_label = LabelOfCollectionFactory(name='🤩YYDS')
        assert with_emoji_label.name

    def test_create(self):
        faker = Faker(locale="zh_CN")
        name = faker.word()
        desc = faker.sentence(nb_words=10)
        color = faker.color()
        _data = {
            "color": color,
            "desc": desc,
            "creator_id": 1,
            "name": name
        }
        _inst = LabelsOfCollection.create(**_data)
        assert _inst
        with pytest.raises(UniqueInstanceError) as e:
            LabelsOfCollection.create(**_data)
        assert '标签名已存在' in str(e)

    def test_has_same_label_name_by_user(self):
        label = LabelOfCollectionFactory()
        new_name = label.name
        user_id = label.creator_id
        has_created = LabelsOfCollection.has_same_label_name_by_user(user_id, new_name)
        assert has_created
        new_user_id = user_id + 1
        has_created = LabelsOfCollection.has_same_label_name_by_user(new_user_id, new_name)
        assert not has_created

    def test_labels_of_user(self):
        user = UserFactory()
        user_inst = User.lookup(user.username)
        user_id = user_inst.id
        assert user_id
        # 没有创建
        labels = LabelsOfCollection.labels_of_user(user_id)
        assert not labels
        # 创建后可以查到
        label = LabelOfCollectionFactory(creator_id=user_id)
        now_has_labels = LabelsOfCollection.labels_of_user(user_id)
        assert label in now_has_labels
        # 新用户没有
        new_user = UserFactory()
        new_user_inst = User.lookup(new_user.username)
        new_user_id = new_user_inst.id
        new_user_labels = LabelsOfCollection.labels_of_user(new_user_id)
        assert not new_user_labels

    def test_label_of_user_by_name(self):
        user = UserFactory()
        user_inst = User.lookup(user.username)
        user_id = user_inst.id
        assert user_id
        # 没有创建
        labels = LabelsOfCollection.label_of_user_by_name(user_id, label_name='测试')
        assert not labels
        # 创建后可以查到
        label = LabelOfCollectionFactory(creator_id=user_id)
        label_name = label.name
        now_has_labels = LabelsOfCollection.label_of_user_by_name(user_id, label_name=label_name)
        assert now_has_labels
        assert now_has_labels.name == label_name
        assert label_name in str(now_has_labels)
        # 新用户没有
        new_user = UserFactory()
        new_user_inst = User.lookup(new_user.username)
        new_user_id = new_user_inst.id
        new_user_labels = LabelsOfCollection.label_of_user_by_name(new_user_id, label_name=label_name)
        assert not new_user_labels


class TestCategoriesOfCollection:

    def teardown(self):
        delete_all_categories()

    def test_factory(self):
        category = CategoryOfCollectionFactory()
        _name = category.name
        assert str(category) == f'<分组 {_name!r}>'
        assert _name
        with_emoji_category = CategoryOfCollectionFactory(name='🤩YYDS')
        assert with_emoji_category.name

    def test_has_same_category_name_by_col(self):
        category_type = random_collection_type()
        label = CategoryOfCollectionFactory(category_type=category_type)
        new_name = label.name
        user_id = label.creator_id
        has_created = CategoriesOfCollection.has_same_category_name_by_col(user_id, category_type, new_name)
        assert has_created
        new_user_id = user_id + 1
        has_created = CategoriesOfCollection.has_same_category_name_by_col(new_user_id, category_type, new_name)
        assert not has_created
