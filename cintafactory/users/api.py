from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db.models import QuerySet
from rest_framework import serializers, viewsets

from .models import BusinessGroup

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False, allow_blank=False)

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "is_active",
            "is_staff",
            "is_superuser",
            "role",
            "business_group",
            "profile_picture",
            "last_login",
            "date_joined",
            "password",
        ]
        read_only_fields = ["id", "last_login", "date_joined"]

    def create(self, validated_data):
        password = validated_data.pop("password", None)
        user = super().create(validated_data)
        if password:
            user.set_password(password)
            user.save(update_fields=["password"])
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        user = super().update(instance, validated_data)
        if password:
            user.set_password(password)
            user.save(update_fields=["password"])
        return user


class BusinessGroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = BusinessGroup
        fields = [
            "id",
            "name",
            "direction",
            "responsible",
            "is_default",
            "business_direction",
        ]


class UserViewSet(viewsets.ModelViewSet):
    serializer_class = UserSerializer
    permission_required_by_action = {
        "list": ["users.view_user"],
        "retrieve": ["users.view_user"],
        "create": ["users.add_user"],
        "update": ["users.change_user"],
        "partial_update": ["users.change_user"],
        "destroy": ["users.delete_user"],
    }

    def get_queryset(self) -> QuerySet:
        return User.objects.select_related("role", "business_group").all()


class BusinessGroupViewSet(viewsets.ModelViewSet):
    serializer_class = BusinessGroupSerializer
    permission_required_by_action = {
        "list": ["users.view_businessgroup"],
        "retrieve": ["users.view_businessgroup"],
        "create": ["users.add_businessgroup"],
        "update": ["users.change_businessgroup"],
        "partial_update": ["users.change_businessgroup"],
        "destroy": ["users.delete_businessgroup"],
    }

    def get_queryset(self) -> QuerySet:
        return BusinessGroup.objects.select_related(
            "direction",
            "responsible",
            "business_direction",
        ).all()
