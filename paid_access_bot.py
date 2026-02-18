#!/usr/bin/env python3
"""
Vagas Remotas - Bot de Controle de Acesso (Canal PAGO)

Funcionalidades:
1. Gera link de convite único por comprador
2. Verifica se usuário está na lista de pagantes
3. Remove usuários que cancelaram/não pagaram
4. Integra com Stripe/Hotmart via webhook

Uso:
- Standalone: python3 paid_access_bot.py
- Com webhook: uvicorn paid_access_bot:app --port 8080
"""

import json
import os
import secrets
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# Telegram
import requests

# FastAPI para webhooks (opcional)
try:
    from fastapi import FastAPI, Request, HTTPException
    from fastapi.responses import JSONResponse
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False

# =============================================================================
# CONFIGURAÇÃO
# =============================================================================

DATA_DIR = Path(__file__).parent / "data"
MEMBERS_DB = DATA_DIR / "paid_members.json"
INVITES_DB = DATA_DIR / "paid_invites.json"

def load_env():
    """Carrega variáveis de ambiente"""
    for path in (
        str(Path(__file__).parent / ".env"),
        str(Path(__file__).parent / ".env.paid"),
    ):
        try:
            if not os.path.exists(path):
                continue
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    v = v.strip().strip('"').strip("'")
                    os.environ[k] = v
        except Exception:
            continue

load_env()

BOT_TOKEN = os.environ.get("TELEGRAM_TOKEN_PAID")
GROUP_ID = os.environ.get("TELEGRAM_CHANNEL_PAID")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET")

# =============================================================================
# DATABASE (JSON simples)
# =============================================================================

def load_members() -> dict:
    """Carrega banco de membros pagantes"""
    if not MEMBERS_DB.exists():
        return {}
    try:
        return json.loads(MEMBERS_DB.read_text())
    except:
        return {}

def save_members(data: dict):
    """Salva banco de membros"""
    MEMBERS_DB.write_text(json.dumps(data, indent=2))

def load_invites() -> dict:
    """Carrega banco de convites pendentes"""
    if not INVITES_DB.exists():
        return {}
    try:
        return json.loads(INVITES_DB.read_text())
    except:
        return {}

def save_invites(data: dict):
    """Salva banco de convites"""
    INVITES_DB.write_text(json.dumps(data, indent=2))

# =============================================================================
# TELEGRAM API
# =============================================================================

def telegram_api(method: str, params: dict = None) -> dict:
    """Chama Telegram Bot API"""
    if not BOT_TOKEN:
        raise RuntimeError("TELEGRAM_TOKEN_PAID não configurado")
    
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    r = requests.post(url, json=params or {}, timeout=15)
    result = r.json()
    
    if not result.get("ok"):
        raise RuntimeError(f"Telegram API error: {result.get('description')}")
    
    return result.get("result", {})

def create_invite_link(expire_hours: int = 24, member_limit: int = 1) -> str:
    """Cria link de convite único para o grupo"""
    if not GROUP_ID:
        raise RuntimeError("TELEGRAM_CHANNEL_PAID não configurado")
    
    expire_date = int(time.time()) + (expire_hours * 3600)
    
    result = telegram_api("createChatInviteLink", {
        "chat_id": GROUP_ID,
        "expire_date": expire_date,
        "member_limit": member_limit,
        "creates_join_request": False
    })
    
    return result.get("invite_link")

def kick_member(user_id: int) -> bool:
    """Remove membro do grupo"""
    if not GROUP_ID:
        return False
    
    try:
        telegram_api("banChatMember", {
            "chat_id": GROUP_ID,
            "user_id": user_id,
            "revoke_messages": False
        })
        # Unban para permitir re-entrada se pagar novamente
        telegram_api("unbanChatMember", {
            "chat_id": GROUP_ID,
            "user_id": user_id,
            "only_if_banned": True
        })
        return True
    except Exception as e:
        print(f"Erro ao remover membro {user_id}: {e}")
        return False

def send_message(chat_id: int, text: str):
    """Envia mensagem para um usuário"""
    try:
        telegram_api("sendMessage", {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML"
        })
    except Exception as e:
        print(f"Erro ao enviar mensagem para {chat_id}: {e}")

# =============================================================================
# LÓGICA DE NEGÓCIO
# =============================================================================

def add_paid_member(email: str, telegram_id: int = None, payment_id: str = None, 
                    platform: str = "manual") -> dict:
    """Adiciona membro pagante"""
    members = load_members()
    
    member = {
        "email": email,
        "telegram_id": telegram_id,
        "payment_id": payment_id,
        "platform": platform,
        "status": "active",
        "joined_at": datetime.now().isoformat(),
        "expires_at": None  # None = vitalício, ou data de expiração
    }
    
    key = email.lower()
    members[key] = member
    save_members(members)
    
    return member

def generate_invite_for_buyer(email: str, payment_id: str = None, 
                               platform: str = "manual") -> str:
    """Gera convite único para comprador"""
    
    # Registra como membro (sem telegram_id ainda)
    add_paid_member(email, payment_id=payment_id, platform=platform)
    
    # Gera link de convite
    invite_link = create_invite_link(expire_hours=72, member_limit=1)
    
    # Salva convite pendente
    invites = load_invites()
    invites[invite_link] = {
        "email": email,
        "payment_id": payment_id,
        "created_at": datetime.now().isoformat(),
        "used": False
    }
    save_invites(invites)
    
    return invite_link

def remove_member_by_email(email: str) -> bool:
    """Remove membro por email (cancelamento)"""
    members = load_members()
    key = email.lower()
    
    if key not in members:
        return False
    
    member = members[key]
    telegram_id = member.get("telegram_id")
    
    # Atualiza status
    member["status"] = "cancelled"
    member["cancelled_at"] = datetime.now().isoformat()
    members[key] = member
    save_members(members)
    
    # Remove do grupo se tiver telegram_id
    if telegram_id:
        kick_member(telegram_id)
        send_message(telegram_id, 
            "⚠️ Sua assinatura do Vagas Remotas Premium foi cancelada.\n\n"
            "Você foi removido do grupo. Para voltar, renove sua assinatura."
        )
    
    return True

def is_member_active(email: str = None, telegram_id: int = None) -> bool:
    """Verifica se membro está ativo"""
    members = load_members()
    
    for member in members.values():
        if email and member.get("email", "").lower() == email.lower():
            return member.get("status") == "active"
        if telegram_id and member.get("telegram_id") == telegram_id:
            return member.get("status") == "active"
    
    return False

def link_telegram_to_email(email: str, telegram_id: int) -> bool:
    """Vincula telegram_id ao email após entrada no grupo"""
    members = load_members()
    key = email.lower()
    
    if key not in members:
        return False
    
    members[key]["telegram_id"] = telegram_id
    members[key]["linked_at"] = datetime.now().isoformat()
    save_members(members)
    
    return True

# =============================================================================
# WEBHOOKS (Stripe, Hotmart, etc)
# =============================================================================

if HAS_FASTAPI:
    app = FastAPI(title="Vagas Remotas - Access Control")
    
    @app.post("/webhook/stripe")
    async def stripe_webhook(request: Request):
        """Webhook do Stripe"""
        payload = await request.body()
        sig_header = request.headers.get("Stripe-Signature")
        
        # Verificar assinatura (simplificado - em produção use stripe.Webhook.construct_event)
        try:
            event = json.loads(payload)
        except:
            raise HTTPException(400, "Invalid payload")
        
        event_type = event.get("type")
        data = event.get("data", {}).get("object", {})
        
        if event_type == "checkout.session.completed":
            # Nova compra
            email = data.get("customer_email")
            payment_id = data.get("id")
            
            if email:
                invite_link = generate_invite_for_buyer(email, payment_id, "stripe")
                # Aqui você pode enviar o link por email ou retornar na resposta
                print(f"✅ Nova compra: {email} → {invite_link}")
        
        elif event_type == "customer.subscription.deleted":
            # Cancelamento
            email = data.get("customer_email")
            if email:
                remove_member_by_email(email)
                print(f"❌ Cancelamento: {email}")
        
        return JSONResponse({"status": "ok"})
    
    @app.post("/webhook/hotmart")
    async def hotmart_webhook(request: Request):
        """Webhook do Hotmart"""
        data = await request.json()
        
        event = data.get("event")
        buyer = data.get("data", {}).get("buyer", {})
        email = buyer.get("email")
        
        if event == "PURCHASE_COMPLETE":
            if email:
                invite_link = generate_invite_for_buyer(email, data.get("id"), "hotmart")
                print(f"✅ Hotmart compra: {email} → {invite_link}")
        
        elif event in ["PURCHASE_REFUNDED", "SUBSCRIPTION_CANCELLATION"]:
            if email:
                remove_member_by_email(email)
                print(f"❌ Hotmart cancelamento: {email}")
        
        return JSONResponse({"status": "ok"})
    
    @app.get("/health")
    async def health():
        return {"status": "ok", "members": len(load_members())}

# =============================================================================
# CLI
# =============================================================================

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Vagas Remotas - Access Control")
    parser.add_argument("--add", metavar="EMAIL", help="Adiciona membro manualmente")
    parser.add_argument("--remove", metavar="EMAIL", help="Remove membro")
    parser.add_argument("--invite", metavar="EMAIL", help="Gera convite para email")
    parser.add_argument("--list", action="store_true", help="Lista membros")
    parser.add_argument("--check", metavar="EMAIL", help="Verifica se email é membro ativo")
    
    args = parser.parse_args()
    
    if args.add:
        member = add_paid_member(args.add, platform="manual")
        print(f"✅ Adicionado: {member}")
    
    elif args.remove:
        if remove_member_by_email(args.remove):
            print(f"✅ Removido: {args.remove}")
        else:
            print(f"❌ Email não encontrado: {args.remove}")
    
    elif args.invite:
        try:
            link = generate_invite_for_buyer(args.invite, platform="manual")
            print(f"✅ Convite gerado para {args.invite}:")
            print(f"   {link}")
        except Exception as e:
            print(f"❌ Erro: {e}")
    
    elif args.list:
        members = load_members()
        print(f"📋 Total de membros: {len(members)}\n")
        for email, data in members.items():
            status = "✅" if data.get("status") == "active" else "❌"
            tg = data.get("telegram_id", "não vinculado")
            print(f"{status} {email} (Telegram: {tg})")
    
    elif args.check:
        active = is_member_active(email=args.check)
        if active:
            print(f"✅ {args.check} é membro ativo")
        else:
            print(f"❌ {args.check} NÃO é membro ativo")
    
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
