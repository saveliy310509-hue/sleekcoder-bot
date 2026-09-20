from aiogram import Router
from bot.handlers.user import router as user_router
from bot.handlers.create import router as create_router
from bot.handlers.admin import router as admin_router

main_router = Router()
main_router.include_router(admin_router)
main_router.include_router(create_router)
main_router.include_router(user_router)
