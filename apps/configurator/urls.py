"""configurator marshrutlari: ACT va konfiguratsiyalar."""

from django.urls import path

from apps.configurator.views import (
    ActViewSet,
    ConfigurationViewSet,
    ConfigurationItemViewSet,
    ConfigurationRequestLineViewSet,
    ConfigurationRequestViewSet,
)
from apps.core.routing import DETAIL, LIST
from apps.core.views import RoadmapView

urlpatterns = [
    path('acts/', ActViewSet.as_view(LIST), name='act-list'),
    path('acts/<int:pk>/', ActViewSet.as_view(DETAIL), name='act-detail'),
    # 20-§3.3: ACT tasdig'i — engineer yuboradi, bugalter (admin) tasdiqlaydi/qaytaradi
    path('acts/<int:pk>/submit/', ActViewSet.as_view({
        'post': 'submit',
    }), name='act-submit'),
    path('acts/<int:pk>/approve/', ActViewSet.as_view({
        'post': 'approve',
    }), name='act-approve'),
    path('acts/<int:pk>/reject/', ActViewSet.as_view({
        'post': 'reject',
    }), name='act-reject'),

    path('configurations/', ConfigurationViewSet.as_view(LIST), name='configuration-list'),
    path('configurations/<int:pk>/', ConfigurationViewSet.as_view(DETAIL), name='configuration-detail'),
    path('configurations/<int:pk>/changes/', ConfigurationViewSet.as_view({
        'get': 'changes',
    }), name='configuration-changes'),
    path('configurations/<int:pk>/stock-check/', ConfigurationViewSet.as_view({
        'get': 'stock_check',
    }), name='configuration-stock-check'),
    # #4: texnik tasdiq zanjiri — engineer submit -> sales approve/reject
    path('configurations/<int:pk>/submit/', ConfigurationViewSet.as_view({
        'post': 'submit',
    }), name='configuration-submit'),
    path('configurations/<int:pk>/approve/', ConfigurationViewSet.as_view({
        'post': 'approve',
    }), name='configuration-approve'),
    path('configurations/<int:pk>/reject/', ConfigurationViewSet.as_view({
        'post': 'reject',
    }), name='configuration-reject'),
    path('configurations/<int:pk>/finalize/', ConfigurationViewSet.as_view({
        'post': 'finalize',
    }), name='configuration-finalize'),
    path('configurations/<int:pk>/assemble/', ConfigurationViewSet.as_view({
        'post': 'assemble',
    }), name='configuration-assemble'),
    # 4-to'plam §2: partiya sonini o'zgartirish — yon ta'sirlari bilan
    path('configurations/<int:pk>/change-quantity/', ConfigurationViewSet.as_view({
        'post': 'change_quantity',
    }), name='configuration-change-quantity'),
    path('configurations/<int:pk>/request-procurement/', ConfigurationViewSet.as_view({
        'post': 'request_procurement',
    }), name='configuration-request-procurement'),
    # YANGI-OQIM B2: narx so'rovi — buyurtma emas, buyurtmachi narx kiritib beradi
    path('configurations/<int:pk>/request-prices/', ConfigurationViewSet.as_view({
        'post': 'request_prices',
    }), name='configuration-request-prices'),
    path('configurations/<int:pk>/export-excel/', ConfigurationViewSet.as_view({
        'get': 'export_excel',
    }), name='configuration-export-excel'),
    # B12: zanjirni bekor qilish — sales (egasi) yoki admin
    path('configurations/<int:pk>/cancel/', ConfigurationViewSet.as_view({
        'post': 'cancel',
    }), name='configuration-cancel'),
    # 14-§5: modelni savdodan chiqarish — butun zanjir emas, bitta model
    path('configurations/<int:pk>/detach/', ConfigurationViewSet.as_view({
        'post': 'detach',
    }), name='configuration-detach'),
    # B8: roadmap — zanjir ko'zgusi (o'z ruxsati, pul yo'q)
    path('configurations/<int:pk>/roadmap/', RoadmapView.as_view(
        kind='configuration',
    ), name='configuration-roadmap'),
    # 9-to'plam §1: aniqlashtirish aylanmasi — savol (engineer) / javob (sales)
    path('configurations/<int:pk>/ask-sales/', ConfigurationViewSet.as_view({
        'post': 'ask_sales',
    }), name='configuration-ask-sales'),
    path('configurations/<int:pk>/answer/', ConfigurationViewSet.as_view({
        'post': 'answer',
    }), name='configuration-answer'),

    path('configuration-requests/', ConfigurationRequestViewSet.as_view(LIST), name='configurationrequest-list'),
    path('configuration-requests/<int:pk>/', ConfigurationRequestViewSet.as_view(DETAIL), name='configurationrequest-detail'),
    path('configuration-requests/<int:pk>/take/', ConfigurationRequestViewSet.as_view({
        'post': 'take',
    }), name='configurationrequest-take'),
    # 14-§7 (2): savdo darajasidagi ACT matni — har yig'ilgan model uchun abzats
    path('configuration-requests/<int:pk>/act-suggestion/', ConfigurationRequestViewSet.as_view({
        'get': 'act_suggestion',
    }), name='configurationrequest-act-suggestion'),
    # 16-§A2: reject bitta manzilda ikkalasiga xizmat qiladi — B15 (zayavka
    # hali `new`, engineer qaytaradi) va savdo darajasidagi qaytarish
    # (modellar sales ko'rigida, izoh bilan draftga qaytadi)
    path('configuration-requests/<int:pk>/reject/', ConfigurationRequestViewSet.as_view({
        'post': 'reject',
    }), name='configurationrequest-reject'),
    path('configuration-requests/<int:pk>/resend/', ConfigurationRequestViewSet.as_view({
        'post': 'resend',
    }), name='configurationrequest-resend'),
    # 9-to'plam §2: engineer ishni hovuzga qaytaradi — boshqa engineer oladi
    path('configuration-requests/<int:pk>/release/', ConfigurationRequestViewSet.as_view({
        'post': 'release',
    }), name='configurationrequest-release'),
    # B17: bekor qilish zayavkadan ham — eng ko'p ishlatiladigan kirish nuqtasi
    path('configuration-requests/<int:pk>/cancel/', ConfigurationRequestViewSet.as_view({
        'post': 'cancel',
    }), name='configurationrequest-cancel'),
    path('configuration-requests/<int:pk>/roadmap/', RoadmapView.as_view(
        kind='request',
    ), name='configurationrequest-roadmap'),
    # 16-§A1: amallar savdo (zayavka) darajasida — A0: qaror savdoniki
    path('configuration-requests/<int:pk>/submit/', ConfigurationRequestViewSet.as_view({
        'post': 'submit',
    }), name='configurationrequest-submit'),
    path('configuration-requests/<int:pk>/approve/', ConfigurationRequestViewSet.as_view({
        'post': 'approve',
    }), name='configurationrequest-approve'),
    path('configuration-requests/<int:pk>/ask-sales/', ConfigurationRequestViewSet.as_view({
        'post': 'ask_sales',
    }), name='configurationrequest-ask-sales'),
    path('configuration-requests/<int:pk>/answer/', ConfigurationRequestViewSet.as_view({
        'post': 'answer',
    }), name='configurationrequest-answer'),
    path('configuration-requests/<int:pk>/request-prices/', ConfigurationRequestViewSet.as_view({
        'post': 'request_prices',
    }), name='configurationrequest-request-prices'),
    path('configuration-requests/<int:pk>/assemble/', ConfigurationRequestViewSet.as_view({
        'post': 'assemble',
    }), name='configurationrequest-assemble'),
    path('configuration-requests/<int:pk>/finalize/', ConfigurationRequestViewSet.as_view({
        'post': 'finalize',
    }), name='configurationrequest-finalize'),
    # 16-§B2: savdo boshlangandan keyin model/tovar qo'shish
    path('configuration-requests/<int:pk>/lines/', ConfigurationRequestViewSet.as_view({
        'post': 'lines',
    }), name='configurationrequest-lines'),

    path('configuration-items/', ConfigurationItemViewSet.as_view(LIST), name='configurationitem-list'),
    path('configuration-items/<int:pk>/', ConfigurationItemViewSet.as_view(DETAIL), name='configurationitem-detail'),

    # 16-§B5(f): tovar qatorini savdodan olib tashlash (model — `detach`)
    path('configuration-request-lines/<int:pk>/', ConfigurationRequestLineViewSet.as_view({
        'get': 'retrieve', 'delete': 'destroy',
    }), name='configurationrequestline-detail'),
]
