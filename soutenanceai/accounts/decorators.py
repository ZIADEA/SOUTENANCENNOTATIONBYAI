"""Décorateurs pour restreindre l'accès aux vues par rôle."""
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def role_required(*roles):
    """Autorise uniquement les utilisateurs ayant l'un des rôles donnés."""
    def decorator(view_func):
        @login_required
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            user = request.user
            if user.is_superuser or user.role in roles:
                return view_func(request, *args, **kwargs)
            raise PermissionDenied("Accès refusé : rôle insuffisant.")
        return _wrapped
    return decorator


professeur_required = role_required('professeur', 'superadmin')
etudiant_required = role_required('etudiant')
superadmin_required = role_required('superadmin')
