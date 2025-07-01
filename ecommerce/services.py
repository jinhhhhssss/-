import uuid
from django.db import transaction, DatabaseError
from django.db.models import F
from .models import Product, Order, OrderItem
import logging
import redis
from django.conf import settings

logger = logging.getLogger(__name__)
class InventoryService:
    @staticmethod
    def process_order_items(order_items_data):
        order = Order.objects.create(
            order_number=str(uuid.uuid4()),
            total_amount=0,
            status=Order.ORDER_STATUS_PENDING
        )
        results = []
        total_amount = 0

        #循环处理订单
        for item_data in order_items_data:
            product_id = item_data.get('product_id')
            print(product_id)
            quantity = item_data.get('quantity', 0)
            try:
                #创建数据库事务的原子块
                with transaction.atomic():
                    # 使用select_for_update()锁定商品行，阻止其他事务进行修改或删除操作
                    product = Product.objects.select_for_update().get(id=product_id)
                    if not product.check_stock_available(quantity):
                        raise ValueError(f"库存不足: 商品ID {product_id}")
                    # 扣减库存
                    product.stock = F('stock') - quantity
                    product.save()
                    product.refresh_from_db()  # 获取最新的库存值

                    # 创建订单项
                    item = OrderItem.objects.create(
                        order=order,
                        product=product,
                        quantity=quantity,
                        price_at_purchase=product.price,
                        status=Order.ORDER_STATUS_SUCCESS
                    )

                    # 更新订单总金额
                    total_amount += product.price * quantity

                    results.append({
                        'product_id': product_id,
                        'success': True,
                        'new_stock': product.stock
                    })
                    # 更新商品缓存
                    product.update_cache()

            except Product.DoesNotExist:
                error_msg = f"商品不存在: 商品ID {product_id}"
                OrderItem.objects.create(
                    order=order,
                    product_id=product_id,
                    quantity=quantity,
                    price_at_purchase=0,
                    status=Order.ORDER_STATUS_FAILED,
                    failure_reason=error_msg
                )
                results.append({
                    'product_id': product_id,
                    'success': False,
                    'reason': error_msg
                })
            except ValueError as e:
                OrderItem.objects.create(
                    order=order,
                    product_id=product_id,
                    quantity=quantity,
                    price_at_purchase=0,
                    status=Order.ORDER_STATUS_FAILED,
                    failure_reason=str(e)
                )
                results.append({
                    'product_id': product_id,
                    'success': False,
                    'reason': str(e)
                })
            except DatabaseError as e:
                logger.error(f"数据库错误处理订单: {e}")
                OrderItem.objects.create(
                    order=order,
                    product_id=product_id,
                    quantity=quantity,
                    price_at_purchase=0,
                    status=Order.ORDER_STATUS_FAILED,
                    failure_reason="数据库操作失败"
                )
                results.append({
                    'product_id': product_id,
                    'success': False,
                    'reason': "数据库操作失败"
                })
            except Exception as e:
                logger.error(f"未知错误处理订单: {e}")
                OrderItem.objects.create(
                    order=order,
                    product_id=product_id,
                    quantity=quantity,
                    price_at_purchase=0,
                    status=Order.ORDER_STATUS_FAILED,
                    failure_reason="未知错误"
                )
                results.append({
                    'product_id': product_id,
                    'success': False,
                    'reason': "未知错误"
                })

        # 更新订单总金额和状态
        order.total_amount = total_amount
        order.status = Order.ORDER_STATUS_SUCCESS if all(r['success'] for r in results) else Order.ORDER_STATUS_FAILED
        order.save()

        return {
            'order_id': order.id,
            'order_number': order.order_number,
            'status': order.status,
            'items': results
        }


class ProductService:
    @staticmethod
    def search_products(keyword=None, cache_only=False):
        if not keyword:
            return []

        # 先尝试从缓存获取
        r = redis.Redis.from_url(settings.REDIS_URL)
        cache_key = f"search:products:{keyword}"

        try:
            cached_results = r.lrange(cache_key, 0, -1)# 获取列表的所有元素
            if cached_results and cache_only:
                return [int(product_id) for product_id in cached_results]

            if cached_results:
                product_ids = [int(product_id) for product_id in cached_results]
                products = []
                for product_id in product_ids:
                    product = Product.get_from_cache(product_id)
                    if product:
                        products.append(product)
                if products:
                    return products
        except Exception as e:
            logger.error(f"缓存查询失败: {e}")
            # 缓存失败时继续查询数据库

        # 缓存未命中或缓存查询失败，查询数据库
        try:
            products = Product.objects.filter(
                name__icontains=keyword,
                is_active=True
            ).order_by('-updated_at')[:50]

            if products:
                # 更新缓存
                product_ids = [str(p.id) for p in products]
                try:
                    r.delete(cache_key)
                    r.rpush(cache_key, *product_ids)
                    r.expire(cache_key, 600)  # 缓存10分钟

                    # 缓存单个商品
                    for product in products:
                        product.update_cache()
                except Exception as e:
                    logger.error(f"更新缓存失败: {e}")

                return products
        except Exception as e:
            logger.error(f"数据库查询失败: {e}")
            return []

        return []

    @staticmethod
    def update_product(product_id, data):
        try:
            with transaction.atomic():
                # 使用select_for_update()锁定商品行，阻止其他事务进行修改或删除操作
                product = Product.objects.select_for_update().get(id=product_id)

                # 更新商品信息
                for field, value in data.items():
                    if hasattr(product, field):
                        setattr(product, field, value)

                product.save()

                # 更新或删除缓存
                if product.is_active and product.stock > 0:
                    product.update_cache()
                else:
                    product.delete_from_cache()

                # 失效搜索缓存
                r = redis.Redis.from_url(settings.REDIS_URL)
                search_keys = r.keys(f"search:products:{product.name[:3]}*")
                if search_keys:
                    r.delete(*search_keys)

                return product
        except Product.DoesNotExist:
            raise ValueError(f"商品不存在: ID {product_id}")
        except Exception as e:
            logger.error(f"更新商品失败: {e}")
            raise