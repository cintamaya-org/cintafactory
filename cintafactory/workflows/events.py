from django.dispatch import Signal


# Payload: instance, transition_event, content_object.
workflow_transitioned = Signal()

