"""Self-service account security; passwords, reset tokens and MFA secrets never enter audit data."""
import base64,secrets,uuid
from datetime import datetime,timezone
from urllib.parse import quote
from fastapi import Depends,HTTPException,Request,Response
from pydantic import BaseModel,ConfigDict,Field
from argon2.exceptions import VerificationError,InvalidHashError
from backend.app import connection,HASHER,COOKIE,digest,Credentials
from backend.security import encrypt,decrypt,verify_totp,throttle
from backend.product import audit,require

class Profile(BaseModel):
    model_config=ConfigDict(extra='forbid')
    display_name:str=Field(max_length=80);language:str=Field(pattern='^(en|ta|si)$')
class Password(BaseModel):
    model_config=ConfigDict(extra='forbid')
    current_password:str=Field(min_length=1,max_length=128);new_password:str=Field(min_length=12,max_length=128);otp:str|None=Field(default=None,max_length=6)
class Challenge(BaseModel):
    model_config=ConfigDict(extra='forbid')
    password:str=Field(min_length=1,max_length=128);otp:str|None=Field(default=None,max_length=6)
class Email(BaseModel):
    model_config=ConfigDict(extra='forbid')
    email:str=Field(min_length=3,max_length=254)
class Reset(BaseModel):
    model_config=ConfigDict(extra='forbid')
    token:str=Field(min_length=30,max_length=128);password:str=Field(min_length=12,max_length=128);otp:str|None=Field(default=None,max_length=6)

def verify_password(conn,user,password,otp=None,require_mfa=True):
    row=conn.execute('SELECT password_hash,email FROM users WHERE id=%s AND is_active FOR UPDATE',(user['id'],)).fetchone()
    if not row or row['email'].endswith('@demo.queuesense.test'):return False
    try:valid=HASHER.verify(row['password_hash'],password)
    except (VerificationError,InvalidHashError):valid=False
    if valid and require_mfa:
        mfa=conn.execute('SELECT * FROM account_mfa WHERE user_id=%s FOR UPDATE',(user['id'],)).fetchone()
        if mfa and mfa['enabled']:
            step=verify_totp(decrypt(mfa['secret_encrypted']),otp,mfa['last_step'])
            valid=step is not None
            if valid:conn.execute('UPDATE account_mfa SET last_step=%s WHERE user_id=%s',(step,user['id']))
    return valid

def attach_accounts(app,settings,current_user,issue_session):
    @app.get('/auth/profile')
    def profile(user=Depends(current_user)):
        with connection(settings) as conn:
            row=conn.execute('SELECT id,email,role,display_name,preferred_language FROM users WHERE id=%s',(user['id'],)).fetchone()
            row['mfa_enabled']=bool(conn.execute('SELECT 1 FROM account_mfa WHERE user_id=%s AND enabled',(user['id'],)).fetchone())
        row['demo_account']=row['email'].endswith('@demo.queuesense.test')
        return row
    @app.post('/auth/profile')
    def save_profile(body:Profile,user=Depends(current_user)):
        with connection(settings) as conn:
            conn.execute('UPDATE users SET display_name=%s,preferred_language=%s WHERE id=%s',(body.display_name.strip(),body.language,user['id']));audit(conn,user,'update_profile','user',user['id'])
        return {'ok':True}
    @app.get('/auth/sessions')
    def sessions(request:Request,user=Depends(current_user)):
        with connection(settings) as conn:
            return conn.execute('SELECT id,created_at,expires_at,device_label,token_hash=%s AS current FROM auth_sessions WHERE user_id=%s AND expires_at>now() ORDER BY created_at DESC',(digest(request.cookies.get(COOKIE,'')),user['id'])).fetchall()
    @app.post('/auth/sessions/{session_id}/revoke')
    def revoke(session_id:uuid.UUID,request:Request,response:Response,user=Depends(current_user)):
        with connection(settings) as conn:
            row=conn.execute('DELETE FROM auth_sessions WHERE id=%s AND user_id=%s RETURNING token_hash',(session_id,user['id'])).fetchone()
            if not row:raise HTTPException(404,'Session not found.')
            audit(conn,user,'revoke_session','user',user['id'])
        current=row['token_hash']==digest(request.cookies.get(COOKIE,''))
        if current:response.delete_cookie(COOKIE,path='/',secure=settings.secure_cookie,httponly=True,samesite='lax')
        return {'ok':True,'current':current}
    @app.post('/auth/password')
    def password(body:Password,request:Request,response:Response,user=Depends(current_user)):
        with connection(settings) as conn:allowed=throttle(conn,'password:'+user['id'])
        if not allowed:raise HTTPException(429,'Try again in 15 minutes.')
        valid=False
        with connection(settings) as conn:
            valid=verify_password(conn,user,body.current_password,body.otp)
            if valid:
                conn.execute('UPDATE users SET password_hash=%s WHERE id=%s',(HASHER.hash(body.new_password),user['id']));conn.execute('DELETE FROM auth_sessions WHERE user_id=%s',(user['id'],));conn.execute('DELETE FROM account_recovery WHERE user_id=%s',(user['id'],));issue_session(conn,user,response,None,request.headers.get('user-agent','Browser session'));audit(conn,user,'change_password','user',user['id'])
        if not valid:raise HTTPException(400,'Current password or authentication code is incorrect. Shared demo credentials cannot be changed.')
        return {'ok':True}
    @app.post('/auth/mfa/setup')
    def setup(body:Challenge,user=Depends(current_user)):
        require(user,('admin',))
        with connection(settings) as conn:allowed=throttle(conn,'mfa:'+user['id'])
        if not allowed:raise HTTPException(429,'Try again in 15 minutes.')
        with connection(settings) as conn:
            if not verify_password(conn,user,body.password,body.otp):raise HTTPException(400,'Password or current authentication code is incorrect. Demo accounts cannot enrol MFA.')
            if conn.execute('SELECT 1 FROM account_mfa WHERE user_id=%s AND enabled',(user['id'],)).fetchone():raise HTTPException(409,'MFA is already enabled. Disable it before enrolling a new authenticator.')
            secret=base64.b32encode(secrets.token_bytes(20)).decode();conn.execute('INSERT INTO account_mfa(user_id,secret_encrypted) VALUES(%s,%s) ON CONFLICT(user_id) DO UPDATE SET secret_encrypted=excluded.secret_encrypted,enabled=false,created_at=now(),last_step=-1',(user['id'],encrypt(secret)))
        return {'secret':secret,'uri':'otpauth://totp/QueueSense:'+quote(user['email'])+'?secret='+secret+'&issuer=QueueSense&digits=6&period=30'}
    @app.post('/auth/mfa/confirm')
    def confirm(body:Challenge,user=Depends(current_user)):
        require(user,('admin',));valid=False
        with connection(settings) as conn:allowed=throttle(conn,'mfa:'+user['id'])
        if not allowed:raise HTTPException(429,'Try again in 15 minutes.')
        with connection(settings) as conn:
            row=conn.execute("SELECT * FROM account_mfa WHERE user_id=%s AND NOT enabled AND created_at>now()-interval '10 minutes' FOR UPDATE",(user['id'],)).fetchone()
            step=verify_totp(decrypt(row['secret_encrypted']),body.otp) if row else None
            valid=step is not None and verify_password(conn,user,body.password,require_mfa=False)
            if valid:conn.execute('UPDATE account_mfa SET enabled=true,last_step=%s WHERE user_id=%s',(step,user['id']));conn.execute('DELETE FROM auth_sessions WHERE user_id=%s',(user['id'],));audit(conn,user,'enable_mfa','user',user['id'])
        if not valid:raise HTTPException(400,'Setup code or password is incorrect or expired.')
        # Enrollment revokes all sessions; next sign-in requires both factors.
        return {'ok':True,'sign_in_required':True}
    @app.post('/auth/mfa/disable')
    def disable(body:Challenge,user=Depends(current_user)):
        require(user,('admin',))
        with connection(settings) as conn:allowed=throttle(conn,'mfa:'+user['id'])
        if not allowed:raise HTTPException(429,'Try again in 15 minutes.')
        valid=False
        with connection(settings) as conn:
            valid=verify_password(conn,user,body.password,body.otp)
            if valid:conn.execute('DELETE FROM account_mfa WHERE user_id=%s',(user['id'],));audit(conn,user,'disable_mfa','user',user['id'])
        if not valid:raise HTTPException(400,'Password or authentication code is incorrect.')
        return {'ok':True}
    @app.post('/auth/recovery/request')
    def request_recovery(body:Email,request:Request):
        email=body.email.strip().lower()
        with connection(settings) as conn:allowed=throttle(conn,'recovery:'+digest(email)+':'+digest(request.client.host if request.client else 'unknown'),3)
        if not allowed:raise HTTPException(429,'Try again in 15 minutes.')
        from backend.delivery import capabilities,mail
        with connection(settings) as conn:
            row=conn.execute('SELECT id,email FROM users WHERE email=%s AND is_active',(email,)).fetchone()
            if row and not email.endswith('@demo.queuesense.test') and capabilities()['email']:
                token=secrets.token_urlsafe(32);conn.execute('DELETE FROM account_recovery WHERE user_id=%s',(row['id'],));conn.execute("INSERT INTO account_recovery(token_hash,user_id,expires_at) VALUES(%s,%s,now()+interval '15 minutes')",(digest(token),row['id']))
                try:mail(email,'QueueSense password recovery code: '+token+'\nUse the Recover account page within 15 minutes. An enabled authenticator is still required.')
                except Exception:conn.execute('DELETE FROM account_recovery WHERE token_hash=%s',(digest(token),))
        return {'ok':True,'message':'If this account is eligible and email delivery is configured, recovery instructions will be sent. Otherwise contact your clinic administrator.'}
    @app.post('/auth/recovery/reset')
    def reset(body:Reset,request:Request):
        with connection(settings) as conn:allowed=throttle(conn,'reset:'+digest(request.client.host if request.client else 'unknown'))
        if not allowed:raise HTTPException(429,'Try again in 15 minutes.')
        valid=False
        with connection(settings) as conn:
            row=conn.execute('SELECT r.*,u.email,u.is_active FROM account_recovery r JOIN users u ON u.id=r.user_id WHERE r.token_hash=%s AND r.expires_at>now() FOR UPDATE OF r',(digest(body.token),)).fetchone()
            if row and row['is_active'] and not row['email'].endswith('@demo.queuesense.test'):
                mfa=conn.execute('SELECT * FROM account_mfa WHERE user_id=%s FOR UPDATE',(row['user_id'],)).fetchone();step=verify_totp(decrypt(mfa['secret_encrypted']),body.otp,mfa['last_step']) if mfa and mfa['enabled'] else None
                valid=not(mfa and mfa['enabled']) or step is not None
                if valid:
                    conn.execute('UPDATE users SET password_hash=%s WHERE id=%s',(HASHER.hash(body.password),row['user_id']));conn.execute('DELETE FROM account_recovery WHERE user_id=%s',(row['user_id'],));conn.execute('DELETE FROM auth_sessions WHERE user_id=%s',(row['user_id'],));audit(conn,{'id':str(row['user_id'])},'recover_password','user',row['user_id'])
                    if step is not None:conn.execute('UPDATE account_mfa SET last_step=%s WHERE user_id=%s',(step,row['user_id']))
        if not valid:raise HTTPException(400,'Recovery code or authenticator code is invalid or expired.')
        return {'ok':True}
    @app.post('/auth/recovery/admin/{user_id}')
    def admin_recovery(user_id:uuid.UUID,body:Challenge,user=Depends(current_user)):
        require(user,('admin',))
        with connection(settings) as conn:allowed=throttle(conn,'admin-recovery:'+user['id'])
        if not allowed:raise HTTPException(429,'Try again in 15 minutes.')
        with connection(settings) as conn:
            if not verify_password(conn,user,body.password,body.otp):raise HTTPException(400,'Password or authentication code is incorrect.')
            target=conn.execute('SELECT id,email FROM users WHERE id=%s AND is_active',(user_id,)).fetchone()
            if not target or target['email'].endswith('@demo.queuesense.test'):raise HTTPException(404,'Eligible account not found.')
            token=secrets.token_urlsafe(32);conn.execute('DELETE FROM account_recovery WHERE user_id=%s',(user_id,));conn.execute("INSERT INTO account_recovery(token_hash,user_id,expires_at) VALUES(%s,%s,now()+interval '15 minutes')",(digest(token),user_id));audit(conn,user,'issue_recovery','user',user_id)
        return {'token':token,'expires_in':900}
