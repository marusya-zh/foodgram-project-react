from rest_framework import mixins, viewsets


class ListViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """
    Вьюсет позволяет вернуть список объектов.
    """
    pass


class ListCreateRetrieveViewSet(mixins.ListModelMixin,
                                mixins.CreateModelMixin,
                                mixins.RetrieveModelMixin,
                                viewsets.GenericViewSet):
    """
    Вьюсет позволяет вернуть список объектов, создать объект, вернуть объект.
    """
    pass


class ListRetrieveViewSet(mixins.ListModelMixin,
                          mixins.RetrieveModelMixin,
                          viewsets.GenericViewSet):
    """
    Вьюсет позволяет вернуть список объектов, вернуть объект.
    """
    pass
