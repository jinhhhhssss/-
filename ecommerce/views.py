from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.core.exceptions import ValidationError
from django.db import OperationalError
import json
import logging

from .models import Product
from .services import InventoryService, ProductService

logger = logging.getLogger(__name__)


@csrf_exempt
@require_http_methods(["POST"])
def process_batch_order(request):
    """订单处理"""
    try:
        data = json.loads(request.body)
        order_items = data.get('items', [])
        if not order_items:
            return JsonResponse({'error': '订单项目不能为空'}, status=400)
        result = InventoryService.process_order_items(order_items)
        return JsonResponse(result, status=201)

    except json.JSONDecodeError:
        return JsonResponse({'error': '无效的JSON格式'}, status=400)
    except ValidationError as e:
        return JsonResponse({'error': str(e)}, status=400)
    except OperationalError as e:
        logger.error(f"数据库操作错误: {e}")
        return JsonResponse({'error': '数据库暂时不可用，请稍后再试'}, status=503)
    except Exception as e:
        logger.error(f"处理订单时发生未知错误: {e}")
        return JsonResponse({'error': '服务器内部错误'}, status=500)


@require_http_methods(["GET"])
def search_products(request):
    try:
        keyword = request.GET.get('keyword', '').strip()
        cache_only = request.GET.get('cache_only', 'true').lower() == 'true'

        if not keyword:
            return JsonResponse({'error': '搜索关键词不能为空'}, status=400)

        products = ProductService.search_products(keyword, cache_only)

        product_list = []
        for product in products:
            product_list.append({
                'id': product.id,
                'name': product.name,
                'description': product.description,
                'price': float(product.price),
                'stock': product.stock,
                'is_active': product.is_active
            })

        return JsonResponse({'products': product_list}, status=200)

    except Exception as e:
        logger.error(f"搜索商品时发生错误: {e}")
        return JsonResponse({'error': '搜索失败，请稍后再试'}, status=500)

def get_all_products(request):
    try:
        products = Product.objects.all()
        product_list = []
        for product in products:
            product_info = {
                'id': product.id,
                'name': product.name,
                'description': product.description,
                'price': float(product.price),
                'stock': product.stock,
                'is_active': product.is_active,
                'created_at': product.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                'updated_at': product.updated_at.strftime('%Y-%m-%d %H:%M:%S')
            }
            product_list.append(product_info)

        return JsonResponse({'products': product_list}, status=200)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
@require_http_methods(["PUT"])
def update_product(request, product_id):
    try:
        data = json.loads(request.body)
        if not data:
            return JsonResponse({'error': '更新数据不能为空'}, status=400)

        product = ProductService.update_product(product_id, data)

        return JsonResponse({
            'id': product.id,
            'name': product.name,
            'price': float(product.price),
            'stock': product.stock,
            'is_active': product.is_active
        }, status=200)

    except json.JSONDecodeError:
        return JsonResponse({'error': '无效的JSON格式'}, status=400)
    except ValueError as e:
        return JsonResponse({'error': str(e)}, status=404)
    except Exception as e:
        logger.error(f"更新商品时发生错误: {e}")
        return JsonResponse({'error': '更新失败，请稍后再试'}, status=500)