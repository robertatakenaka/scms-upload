from datetime import datetime

from django.shortcuts import get_object_or_404

from .models import ErrorResolution, ErrorResolutionOpinion, Package, ValidationError, choices


def add_validation_error(error_category, package_id, package_status, message=None, data=None):
    ve = ValidationError()
    ve.category = error_category

    ve.package = get_object_or_404(Package, pk=package_id)
    ve.package.status = package_status
    ve.message = message
    ve.data = data

    ve.package.save()
    ve.save()


def upsert_validation_error_resolution(validation_error_id, user, action, comment):
    er = upsert_object(ErrorResolution, validation_error_id, user)
    er.action = action
    er.comment = comment
    er.validation_error = ValidationError.objects.get(pk=validation_error_id)
    er.save()


def upsert_validation_error_resolution_opinion(validation_error_id, user, opinion, comment):
    ero = upsert_object(ErrorResolutionOpinion, validation_error_id, user)

    ero.opinion = opinion
    ero.comment = comment
    ero.validation_error = ValidationError.objects.get(pk=validation_error_id)

    ero.save()


def upsert_object(object_class, validation_error_id, user):
    try:
        obj_instance = object_class.objects.get(pk=validation_error_id)
        obj_instance.updated = datetime.now()
        obj_instance.updated_by = user
    except object_class.DoesNotExist:
        obj_instance = object_class()
        obj_instance.creator = user
        obj_instance.created = datetime.now()

    return obj_instance


def update_package_check_finish(package_id):
    package = get_object_or_404(Package, pk=package_id)

    if package.status == choices.PS_READY_TO_BE_FINISHED:
        package.status = choices.PS_QA
        package.save()
        return True

    return False


def update_package_check_errors(package_id):
    package = get_object_or_404(Package, pk=package_id)

    for category in [ve.resolution.action for ve in package.validationerror_set.all()]:
        if category == choices.ER_ACTION_TO_FIX or category == '':
            package.status = choices.PS_PENDING_CORRECTION    
            package.save()

            return

    package.status = choices.PS_READY_TO_BE_FINISHED
    package.save()
