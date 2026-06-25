from django.conf import settings


def nav_home_url(request):
    host_ip = request.get_host().split(':')[0]
    mapping = getattr(settings, 'DOWNLOAD_REVIEW_NAV_HOME_BY_HOST', {})
    return {'nav_home_url': mapping.get(host_ip, '')}
