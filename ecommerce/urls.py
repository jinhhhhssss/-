from django.urls import path
from .views import process_batch_order, search_products, update_product, get_all_products

urlpatterns = [
    path('api/orders/batch/', process_batch_order, name='batch-order'),
    path('api/products/all/', get_all_products, name='get-all-products'),
    path('api/products/search/', search_products, name='product-search'),
    path('api/products/<int:product_id>/', update_product, name='update-product'),
]