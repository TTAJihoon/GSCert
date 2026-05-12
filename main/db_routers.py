from django.conf import settings


class WorkflowDatabaseRouter:
    workflow_app_label = "main"

    def _workflow_alias(self):
        return getattr(settings, "WORKFLOW_DATABASE_ALIAS", "workflow")

    def _workflow_model_names(self):
        return {
            name.lower()
            for name in getattr(settings, "WORKFLOW_MODEL_NAMES", set())
        }

    def _is_workflow_model(self, app_label, model_name):
        return (
            app_label == self.workflow_app_label
            and model_name
            and model_name.lower() in self._workflow_model_names()
        )

    def db_for_read(self, model, **hints):
        if self._is_workflow_model(model._meta.app_label, model._meta.model_name):
            return self._workflow_alias()
        return None

    def db_for_write(self, model, **hints):
        if self._is_workflow_model(model._meta.app_label, model._meta.model_name):
            return self._workflow_alias()
        return None

    def allow_relation(self, obj1, obj2, **hints):
        model1_is_workflow = self._is_workflow_model(
            obj1._meta.app_label,
            obj1._meta.model_name,
        )
        model2_is_workflow = self._is_workflow_model(
            obj2._meta.app_label,
            obj2._meta.model_name,
        )
        if model1_is_workflow or model2_is_workflow:
            return model1_is_workflow and model2_is_workflow
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        workflow_alias = self._workflow_alias()
        is_workflow_model = self._is_workflow_model(app_label, model_name)

        if is_workflow_model:
            return db == workflow_alias
        if db == workflow_alias:
            return False
        return None
