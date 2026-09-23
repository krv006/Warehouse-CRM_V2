"""sales marshrutlari: og'zaki kelishuv va shartnomalar."""

from django.urls import path

from apps.core.routing import DETAIL, LIST, READ_DETAIL, READ_LIST
from apps.core.views import RoadmapView
from apps.sales.views import (
    ContractViewSet,
    ContractItemViewSet,
    ContractApprovalViewSet,
    ContractPaymentViewSet,
    LeadViewSet,
    WopiFileContentsView,
    WopiFileInfoView,
)

urlpatterns = [
    path('leads/', LeadViewSet.as_view(LIST), name='lead-list'),
    path('leads/<int:pk>/', LeadViewSet.as_view(DETAIL), name='lead-detail'),

    path('contracts/', ContractViewSet.as_view(LIST), name='contract-list'),
    path('contracts/deadlines/', ContractViewSet.as_view({
        'get': 'deadlines',
    }), name='contract-deadlines'),
    path('contracts/<int:pk>/', ContractViewSet.as_view(DETAIL), name='contract-detail'),
    path('contracts/<int:pk>/submit/', ContractViewSet.as_view({
        'post': 'submit',
    }), name='contract-submit'),
    path('contracts/<int:pk>/approve/', ContractViewSet.as_view({
        'post': 'approve',
    }), name='contract-approve'),
    path('contracts/<int:pk>/reject/', ContractViewSet.as_view({
        'post': 'reject',
    }), name='contract-reject'),
    path('contracts/<int:pk>/confirm-payment/', ContractViewSet.as_view({
        'post': 'confirm_payment',
    }), name='contract-confirm-payment'),
    # #2: yetkazish alohida hodisa — mol shu yerda chiqadi (buyurtmachi/bugalter)
    path('contracts/<int:pk>/ship/', ContractViewSet.as_view({
        'post': 'ship',
    }), name='contract-ship'),
    # B12: zanjirni bekor qilish — sales (egasi) yoki admin
    path('contracts/<int:pk>/cancel/', ContractViewSet.as_view({
        'post': 'cancel',
    }), name='contract-cancel'),
    # B8: roadmap — zanjir ko'zgusi (o'z ruxsati, pul yo'q)
    path('contracts/<int:pk>/roadmap/', RoadmapView.as_view(
        kind='contract',
    ), name='contract-roadmap'),
    # B3: Didox ikki qadam — yubordim / Didox tasdiqladi (bugalter)
    path('contracts/<int:pk>/send-didox/', ContractViewSet.as_view({
        'post': 'send_didox',
    }), name='contract-send-didox'),
    path('contracts/<int:pk>/confirm-didox/', ContractViewSet.as_view({
        'post': 'confirm_didox',
    }), name='contract-confirm-didox'),
    path('contracts/<int:pk>/request-procurement/', ContractViewSet.as_view({
        'post': 'request_procurement',
    }), name='contract-request-procurement'),
    path('contracts/<int:pk>/timeline/', ContractViewSet.as_view({
        'get': 'timeline',
    }), name='contract-timeline'),
    path('contracts/<int:pk>/print/', ContractViewSet.as_view({
        'get': 'print_form',
    }), name='contract-print'),
    # 13-§1: shartnoma matni — bugalter yuklaydi va saytda ko'rinadi.
    # QOLGAN-ISHLAR-2 §4: `PUT` olib tashlandi — 15-§A dan keyin Didoxga
    # `source_file` ketadi, `body`ni alohida tahrirlash ikkinchi (eski)
    # manba yaratardi. O'qish (`GET`) va yuklash (`upload/`) qoladi.
    path('contracts/<int:pk>/document/', ContractViewSet.as_view({
        'get': 'document',
    }), name='contract-document'),
    path('contracts/<int:pk>/document/upload/', ContractViewSet.as_view({
        'post': 'document_upload',
    }), name='contract-document-upload'),
    path('contracts/<int:pk>/document/versions/', ContractViewSet.as_view({
        'get': 'document_versions',
    }), name='contract-document-versions'),
    # 15-§A: Collabora Online (WOPI) — brauzerda to'g'ridan-to'g'ri tahrirlash
    path('contracts/<int:pk>/document/edit-session/', ContractViewSet.as_view({
        'post': 'document_edit_session',
    }), name='contract-document-edit-session'),
    # WOPI host — Collabora shu ikkitasini so'raydi; slashsiz ataylab (WOPI
    # klienti WOPISrc'ga "/contents"ni to'g'ridan-to'g'ri ulab chaqiradi)
    path('wopi/files/<int:pk>', WopiFileInfoView.as_view(), name='wopi-file-info'),
    path('wopi/files/<int:pk>/contents', WopiFileContentsView.as_view(), name='wopi-file-contents'),

    path('contract-items/', ContractItemViewSet.as_view(LIST), name='contractitem-list'),
    path('contract-items/<int:pk>/', ContractItemViewSet.as_view(DETAIL), name='contractitem-detail'),

    path('contract-payments/', ContractPaymentViewSet.as_view(LIST), name='contractpayment-list'),
    path('contract-payments/<int:pk>/', ContractPaymentViewSet.as_view(DETAIL), name='contractpayment-detail'),

    path('contract-approvals/', ContractApprovalViewSet.as_view(READ_LIST), name='contractapproval-list'),
    path('contract-approvals/<int:pk>/', ContractApprovalViewSet.as_view(READ_DETAIL), name='contractapproval-detail'),
]
