# -*- coding: utf-8 -*-

from copy import deepcopy

from django.conf import settings
from django.contrib import admin
from django.core.exceptions import ImproperlyConfigured

from django.urls import resolve, Resolver404


class ModelAdminReorderMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

# REMOVE        
#    def init_config(self, request, app_list):
#        self.request = request
#        self.app_list = app_list

        self.config = getattr(settings, 'ADMIN_REORDER', None)
        if not self.config:
            # ADMIN_REORDER settings is not defined.
            raise ImproperlyConfigured('ADMIN_REORDER config is not defined.')

        # ADMIN_REORDER should be a dict keyed to admin sites
        if not isinstance(self.config, (dict)):
            raise ImproperlyConfigured(
                'ADMIN_REORDER config parameter must be a dict. '
                'Got {config}'.format(config=self.config))
        else:
            tested = [isinstance(v, (tuple, list)) for v in self.config.values()]
            if sum(tested) != len(self.config.values()):
                raise ImproperlyConfigured(
                    'ADMIN_REORDER config must be a dict with tuple or list values. '
                    'Got {config}'.format(config=self.config))
    
    def __call__(self, request):
        # executed for each request before the view (and later middleware) are called.
        self.admin_site_name = None
        return self.get_response(request)

        """REMOVE
        admin_index = admin.site.index(request)
        try:
            # try to get all installed models
            app_list = admin_index.context_data['app_list']
        except KeyError:
            # use app_list from context if this fails
            pass

        # Flatten all models from apps
        self.models_list = []
        for app in app_list:
            for model in app['models']:
                model['model_name'] = self.get_model_name(
                    app['app_label'], model['object_name'])
                self.models_list.append(model)
        """

    def get_app_list(self):
        ordered_app_list = []
        for app_config in self.config[self.admin_site_name or '']:
            app = self.make_app(app_config)
            if app:
                ordered_app_list.append(app)
        return ordered_app_list

    def make_app(self, app_config):
        if not isinstance(app_config, (dict, str)):
            raise TypeError('ADMIN_REORDER list item must be '
                            'dict or string. Got %s' % repr(app_config))

        if isinstance(app_config, str):
            # Keep original label and models
            return self.find_app(app_config)
        else:
            return self.process_app(app_config)

    def find_app(self, app_label):
        for app in self.app_list:
            if app['app_label'] == app_label:
                return app

    def get_model_name(self, app_name, model_name):
        if '.' not in model_name:
            model_name = '%s.%s' % (app_name, model_name)
        return model_name

    def process_app(self, app_config):
        if 'app' not in app_config:
            raise NameError('ADMIN_REORDER list item must define '
                            'a "app" name. Got %s' % repr(app_config))

        app = self.find_app(app_config['app'])
        if app:
            app = deepcopy(app)
            # Rename app
            if 'label' in app_config:
                app['name'] = app_config['label']

            # Process app models
            if 'models' in app_config:
                models_config = app_config.get('models')
                models = self.process_models(models_config)
                if models:
                    app['models'] = models
                else:
                    return None
            return app

    def process_models(self, models_config):
        if not isinstance(models_config, (dict, list, tuple)):
            raise TypeError('"models" config for ADMIN_REORDER list '
                            'item must be dict or list/tuple. '
                            'Got %s' % repr(models_config))

        ordered_models_list = []
        for model_config in models_config:
            model = None
            if isinstance(model_config, dict):
                model = self.process_model(model_config)
            else:
                model = self.find_model(model_config)

            if model:
                ordered_models_list.append(model)

        return ordered_models_list

    def find_model(self, model_name):
        for model in self.models_list:
            if model['model_name'] == model_name:
                return model

    def process_model(self, model_config):
        # Process model defined as { model: 'model', 'label': 'label' }
        for key in ('model', 'label', ):
            if key not in model_config:
                return
        model = self.find_model(model_config['model'])
        if model:
            model['name'] = model_config['label']
            return model
    
    def process_view(self, request, view_func, *args, **kwargs):
        try:
            admin_site = view_func.admin_site
        except AttributeError:
            # not an admin site
            return
        
        if admin_site.name in self.config:
            self.admin_site_name = admin_site.name
        else:
            # no ordering set for this site
            return
        
        try:
            # try to get all installed models
            self.app_list = admin_site.index(request).context_data['app_list']
        except KeyError:
            # no app_list in the view context
            return
        
        # Flatten all models from apps
        self.models_list = []
        for app in self.app_list:
            for model in app['models']:
                model['model_name'] = self.get_model_name(
                    app['app_label'], model['object_name'])
                self.models_list.append(model)
    
    def process_template_response(self, request, response):
        if self.admin_site_name is None:
            # no configuration available
            return response

        try:
            url = resolve(request.path_info)
        except Resolver404:
            return response
        if not url.app_name == 'admin' and \
                url.url_name not in ['index', 'app_list']:
            # current view is not a django admin index
            # or app_list view, bail out!
            return response

        if 'app_list' in response.context_data:
            self.app_list = response.context_data['app_list']
            context_key = 'app_list'
        # handle django 3.1 sidebar
        elif 'available_apps' in response.context_data:
            self.app_list = response.context_data['available_apps']
            context_key = 'available_apps'
        else:  # nothing to reorder, return response
            return response

        ordered_app_list = self.get_app_list()
        response.context_data[context_key] = ordered_app_list
        return response
