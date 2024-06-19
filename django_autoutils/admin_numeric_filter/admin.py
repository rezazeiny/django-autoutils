from django.contrib import admin
from django.db.models import Max, Min
from django.db.models.fields import DecimalField, FloatField, IntegerField, AutoField

from .forms import RangeNumericForm, SingleNumericForm, SliderNumericForm


class NumericFilterModelAdmin(admin.ModelAdmin):
    class Media:
        css = {
            "all": (
                "js/nouislider.min.css",
                "css/admin-numeric-filter.css",
            )
        }
        js = (
            "js/wNumb.min.js",
            "js/nouislider.min.js",
            "js/admin-numeric-filter.js",
        )


class SingleNumericFilter(admin.FieldListFilter):
    request = None
    parameter_name = None
    template = "admin/filter_numeric_single.html"

    def __init__(self, field, request, params, model, model_admin, field_path):
        super().__init__(field, request, params, model, model_admin, field_path)
        if not isinstance(field, (DecimalField, IntegerField, FloatField, AutoField)):
            raise TypeError("Class {} is not supported for {}.".format(type(self.field), self.__class__.__name__))

        self.request = request
        if self.parameter_name is None:
            self.parameter_name = self.field_path
        if self.parameter_name in params:
            value = params.pop(self.parameter_name)
            self.used_parameters[self.parameter_name] = value

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(**{self.parameter_name: self.value()})

    def value(self):
        return self.used_parameters.get(self.parameter_name, None)

    def expected_parameters(self):
        return [self.parameter_name]

    def choices(self, changelist):
        return ({
                    "request": self.request,
                    "parameter_name": self.parameter_name,
                    "form": SingleNumericForm(name=self.parameter_name, data={self.parameter_name: self.value()}),
                },)


class RangeNumericFilter(admin.FieldListFilter):
    request = None
    parameter_name = None
    template = "admin/filter_numeric_range.html"

    def __init__(self, field, request, params, model, model_admin, field_path):
        super().__init__(field, request, params, model, model_admin, field_path)
        if not isinstance(field, (DecimalField, IntegerField, FloatField, AutoField)):
            raise TypeError("Class {} is not supported for {}.".format(type(self.field), self.__class__.__name__))

        self.request = request
        if self.parameter_name is None:
            self.parameter_name = self.field_path

        if self.parameter_name_from in params:
            value = params.pop(self.field_path + "_from")
            self.used_parameters[self.field_path + "_from"] = value

        if self.parameter_name_to in params:
            value = params.pop(self.field_path + "_to")
            self.used_parameters[self.field_path + "_to"] = value

    @property
    def parameter_name_from(self):
        return f"{self.parameter_name}_from"

    @property
    def parameter_name_to(self):
        return f"{self.parameter_name}_to"

    def queryset(self, request, queryset):
        filters = {}
        value_from = self.get_parameter(self.parameter_name_from)
        if value_from is not None and value_from != "":
            filters.update({
                self.parameter_name + "__gte": self.get_parameter(self.parameter_name_from),
            })

        value_to = self.get_parameter(self.parameter_name_to)
        if value_to is not None and value_to != "":
            filters.update({
                self.parameter_name + "__lte": self.get_parameter(self.parameter_name_to),
            })
        return queryset.filter(**filters)

    def expected_parameters(self):
        return [{self.parameter_name_from}, {self.parameter_name_to}]

    def choices(self, changelist):
        return ({
                    "request": self.request,
                    "parameter_name": self.parameter_name,
                    "form": RangeNumericForm(name=self.parameter_name, data={
                        self.parameter_name_from: self.get_parameter(self.parameter_name_from),
                        self.parameter_name_to: self.get_parameter(self.parameter_name_to),
                    }),
                },)

    def get_parameter(self, key, default=None):
        parameter = self.used_parameters.get(key, default)
        if hasattr(parameter, "__iter__"):
            for item in parameter:
                return item
            return default
        return parameter


class SliderNumericFilter(RangeNumericFilter):
    MAX_DECIMALS = 7
    STEP = None

    template = "admin/filter_numeric_slider.html"
    field = None

    def __init__(self, field, request, params, model, model_admin, field_path):
        super().__init__(field, request, params, model, model_admin, field_path)

        self.field = field
        self.q = model_admin.get_queryset(request)

    def choices(self, changelist):
        total = self.q.all().count()
        min_value = self.q.all().aggregate(
            min=Min(self.parameter_name)
        ).get("min", 0)

        if total > 1:
            max_value = self.q.all().aggregate(
                max=Max(self.parameter_name)
            ).get("max", 0)
        else:
            max_value = None

        if isinstance(self.field, (FloatField, DecimalField)):
            decimals = self.MAX_DECIMALS
            step = self.STEP if self.STEP else self._get_min_step(self.MAX_DECIMALS)
        else:
            decimals = 0
            step = self.STEP if self.STEP else 1

        return ({
                    "decimals": decimals,
                    "step": step,
                    "parameter_name": self.parameter_name,
                    "request": self.request,
                    "min": min_value,
                    "max": max_value,
                    "value_from": self.get_parameter(self.parameter_name_from, min_value),
                    "value_to": self.get_parameter(self.parameter_name_to, max_value),
                    "form": SliderNumericForm(name=self.parameter_name, data={
                        self.parameter_name_from: self.get_parameter(self.parameter_name_from, min_value),
                        self.parameter_name_to: self.get_parameter(self.parameter_name_to, max_value),
                    })
                },)

    def _get_min_step(self, precision):
        result_format = "{{:.{}f}}".format(precision - 1)
        return float(result_format.format(0) + "1")
