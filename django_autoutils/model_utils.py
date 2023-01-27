"""
    All utils for model
"""
import logging
import os
import string
from typing import Callable

from autoutils.script import id_generator
from django.contrib.auth import get_user_model
from django.contrib.messages import add_message
from django.db import models, transaction, IntegrityError, OperationalError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from rest_framework import exceptions

from django_autoutils.exceptions import RequestException
from django_autoutils.utils import get_request_obj

logger = logging.getLogger("django_autoutils")


def slug_generator(first_char_size=3, num_size=4, last_char_size=3):
    """
        Generate slug
    """
    # noinspection PyTypeChecker
    return (f"{id_generator(first_char_size, string.ascii_uppercase)}"
            f"{id_generator(num_size, string.digits)}"
            f"{id_generator(last_char_size, string.ascii_uppercase)}")


def model_transaction(nowait=False, just_check=False, current_user=False):
    """
        Use this decorator for run input function in transaction
    """

    def inner(func: Callable):
        """
            Class decorator for run in transaction
        """

        def wrapper(obj, request, *args, **kwargs):
            """
                Wrapper function for handle extra functions before main function
            Args:
                obj (AbstractModel):
                request: django request
                *args: extra data
                **kwargs: extra data
            """
            if current_user:
                use_obj = request.user
            else:
                use_obj = obj
            if use_obj.is_in_updating(nowait=nowait or just_check):
                use_obj.message_log(request, logging.ERROR, f"last progress not finished yet")
                return
            if just_check:
                func(obj, request, *args, **kwargs)
                return
            try:
                with transaction.atomic():
                    use_obj.select_for_update()
                    return func(obj, request, *args, **kwargs)
            except IntegrityError:
                obj.message_log(request, logging.ERROR, f"error run in transaction function {func.__name__}")

        return wrapper

    return inner


def view_transaction(get_object: "Callable" = None, nowait=False):
    """
        Use this decorator for update user related
    """

    def inner(func: "Callable"):
        """
            Class decorator for run in transaction
        """

        def wrapper(view, request, *args, **kwargs):
            """
                Wrapper function for handle extra functions before main function
            Args:
                view: view object
                request: django request
                *args: extra data
                **kwargs: extra data
            """
            if callable(get_object):
                update_object = get_object(view, request)
            else:
                update_object = request.user
                user_model = get_user_model()
                if not isinstance(update_object, user_model):
                    raise exceptions.AuthenticationFailed("can not find user")
            if update_object.is_in_updating(nowait=nowait):
                update_object.message_log(request, logging.ERROR, f"last progress not finished yet")
                raise RequestException(request)
            try:
                with transaction.atomic():
                    new_update_object = update_object.select_for_update()
                    return func(view, request, new_update_object, *args, **kwargs)
            except IntegrityError as e:
                update_object.message_log(request, logging.ERROR, f"error run in transaction function {func.__name__}")
                update_object.log(logging.ERROR, f"error run in transaction function {func.__name__}. error: {e}")
                raise RequestException(request)

        return wrapper

    return inner


def time_random_generator():
    """
        Get random char by time
    """
    # noinspection PyTypeChecker
    random_char = id_generator(size=8, chars=string.ascii_lowercase + string.digits)
    now_time = hex(int(timezone.now().timestamp()))[2:]
    return f"{now_time}{random_char}"


def upload_file(instance, filename=None) -> str:
    """
        Upload user image
    """
    filename, file_extension = os.path.splitext(filename)
    path = os.path.join(f"{instance.__class__.__name__}", f"{time_random_generator()}{file_extension}")
    return path


class AbstractModel(models.Model):
    """
        All models must be extended this model
    """
    BASE_PERMISSION_OBJECT = None
    LOGGER = logger
    is_active = models.BooleanField(_("is active"), default=True)
    insert_dt = models.DateTimeField(_("insert time"), auto_now_add=True)
    update_dt = models.DateTimeField(_("update time"), auto_now=True)

    class Meta:
        abstract = True

    def _get_message(self, message):
        return f"'{self}': {message}"

    def _set_log_data(self, data: dict):
        pass

    @classmethod
    def class_log(cls, level: int, message: str, extra: dict = None):
        if extra is None:
            extra = {}
        if cls.LOGGER.isEnabledFor(level):
            # noinspection PyProtectedMember
            cls.LOGGER._log(level, message, (), extra=extra)

    def log(self, level: int, message: str, extra: dict = None):
        """
            Use for all logs
        """
        if extra is None:
            extra = {}
        if self.LOGGER.isEnabledFor(level):
            self._set_log_data(extra)
            # noinspection PyProtectedMember
            self.LOGGER._log(level, self._get_message(message), (), extra=extra)

    @classmethod
    def class_message_log(cls, request, level: int, message: str, extra: dict = None):
        if request is None:
            request = get_request_obj()
        if request is not None:
            add_message(request, level, message)
        cls.class_log(level=level, message=message, extra=extra)

    def message_log(self, request, level: int, message: str, extra: dict = None):
        """
            For message log
        """
        if request is None:
            request = get_request_obj()
        if request is not None:
            add_message(request, level, self._get_message(message))
        self.log(level=level, message=message, extra=extra)

    def get_obj(self):
        """
            Get object for permission
        """
        # noinspection PyUnresolvedReferences
        if self.id is None:
            return None
        return self._get_obj()

    def _get_obj(self):
        if self.BASE_PERMISSION_OBJECT is None:
            return self
        base_object = getattr(self, self.BASE_PERMISSION_OBJECT, None)
        if base_object is None:
            return None
        return base_object.get_obj()

    def select_for_update(self, nowait=False):
        """
            Check last state is in running

            Returns:
                (bool) : for select for update an object.
        """
        try:
            return self.queryset().select_for_update(nowait=nowait).get()
        except OperationalError:
            return None

    def is_in_updating(self, nowait=True):
        """
            Check last state is in running

            Returns:
                (bool) : true for if it is in updating
        """
        try:
            with transaction.atomic():
                return not bool(self.select_for_update(nowait=nowait))
        except Exception as e:
            self.log(logging.ERROR, f"it is in running. {e}")
            return True

    def queryset(self) -> "models.QuerySet":
        """
            Get queryset of one object
        """
        # noinspection PyUnresolvedReferences
        return self.__class__.objects.filter(id=self.id)

    def update_data(self, data: dict):
        """
            Update one object
        """
        return self.queryset().update(**data)


class AbstractSlugModel(AbstractModel):
    slug = models.SlugField(unique=True, editable=False, blank=True)

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        """
            Add slug
        """
        while not self.slug:
            new_slug = slug_generator()
            # noinspection PyUnresolvedReferences
            if not self.__class__.objects.filter(slug=new_slug).exists():
                self.slug = new_slug
        super().save(*args, **kwargs)
