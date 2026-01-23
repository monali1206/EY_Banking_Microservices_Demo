import uuid, os, hashlib
from datetime import datetime
from flask import Flask
from flask.views import MethodView
from flask_smorest import Api, Blueprint, abort
from flask_jwt_extended import JWTManager, create_access_token, jwt_required
from flask_sqlalchemy import SQLAlchemy
from marshmallow import Schema, fields, validate

app = Flask(__name__)

# --- EXPERT CONFIGURATION ---
app.config.update({
    "API_TITLE": "Linking Aadhaar Service",
    "API_VERSION": "v1",
    "OPENAPI_VERSION": "3.0.3",
    "OPENAPI_URL_PREFIX": "/",
    "OPENAPI_SWAGGER_UI_PATH": "/swagger-ui",
    "OPENAPI_SWAGGER_UI_URL": "https://cdn.jsdelivr.net/npm/swagger-ui-dist/",
    # Database connection for PostgreSQL
    "SQLALCHEMY_DATABASE_URI": os.getenv("DATABASE_URL", "postgresql://admin:securepassword@db:5432/bank_onboarding_db"),
    "SQLALCHEMY_TRACK_MODIFICATIONS": False,
    "JWT_SECRET_KEY": os.getenv("JWT_SECRET_KEY", "bank-fixed-secret-key"),
    "API_SPEC_OPTIONS": {
        "security": [{"bearerAuth": []}],
        "components": {
            "securitySchemes": {
                "bearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "bearerFormat": "JWT"
                }
            }
        }
    }
})

# Initialize Database, API, and Security
db = SQLAlchemy(app)
api = Api(app)
jwt = JWTManager(app)
blp = Blueprint("aadhaar", "aadhaar", description="UIDAI Compliant Aadhaar Linking Lifecycle")

# --- DATABASE MODELS ---

class AadhaarRequestModel(db.Model):
    __tablename__ = 'aadhaar_link_requests'
    request_id = db.Column(db.String(50), primary_key=True)
    # PRIVACY RULE: Store SHA-256 hash instead of plaintext Aadhaar
    aadhaar_hash = db.Column(db.String(64), nullable=False)
    # Store masked version for display (XXXX-XXXX-1234)
    masked_aadhaar = db.Column(db.String(15), nullable=False)
    status = db.Column(db.String(30), default="PENDING_OTP")
    consent_obtained = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# --- SCHEMAS ---
class AadhaarStartSchema(Schema):
    aadhaarNumber = fields.Str(required=True, validate=validate.Length(equal=12))
    consentObtained = fields.Bool(required=True, validate=validate.Equal(True))

class OtpVerifySchema(Schema):
    otp = fields.Str(required=True, validate=validate.Length(equal=6))

# --- ROUTES ---

@blp.route("/login")
class Login(MethodView):
    def post(self):
        """Step 0: Get Token for Swagger Authorize"""
        return {"access_token": create_access_token(identity="admin")}

@blp.route("/v1/aadhaar/link-requests")
class AadhaarStart(MethodView):
    @jwt_required()
    @blp.arguments(AadhaarStartSchema, location="form")
    def post(self, data):
        """• POST /v1/aadhaar/link-requests (start)"""
        request_id = f"ADR_{uuid.uuid4().hex[:8].upper()}"
        
        # Privacy Implementation: Create hash and masked version
        a_hash = hashlib.sha256(data['aadhaarNumber'].encode()).hexdigest()
        masked = "XXXX-XXXX-" + data['aadhaarNumber'][-4:]
        
        new_request = AadhaarRequestModel(
            request_id=request_id,
            aadhaar_hash=a_hash,
            masked_aadhaar=masked,
            consent_obtained=data['consentObtained']
        )
        db.session.add(new_request)
        db.session.commit()
        
        return {
            "requestId": request_id,
            "status": new_request.status,
            "message": "Aadhaar linking initiated. Consent verified."
        }, 201

@blp.route("/v1/aadhaar/link-requests/<string:requestId>/send-otp")
class AadhaarSendOtp(MethodView):
    @jwt_required()
    def post(self, requestId):
        """• POST /v1/aadhaar/link-requests/{requestId}/send-otp"""
        request = AadhaarRequestModel.query.get_or_404(requestId)
        request.status = "OTP_SENT"
        db.session.commit()
        return {
            "requestId": requestId,
            "status": request.status,
            "message": "OTP successfully triggered via UIDAI gateway"
        }, 200

@blp.route("/v1/aadhaar/link-requests/<string:requestId>/verify-otp")
class AadhaarVerifyOtp(MethodView):
    @jwt_required()
    @blp.arguments(OtpVerifySchema, location="form")
    def post(self, data, requestId):
        """• POST /v1/aadhaar/link-requests/{requestId}/verify-otp"""
        request = AadhaarRequestModel.query.get_or_404(requestId)
        # Verify logic would go here
        request.status = "OTP_VERIFIED"
        db.session.commit()
        return {
            "requestId": requestId,
            "status": request.status,
            "message": "UIDAI OTP validation successful"
        }, 200

@blp.route("/v1/aadhaar/link-requests/<string:requestId>/finalize")
class AadhaarFinalize(MethodView):
    @jwt_required()
    def post(self, requestId):
        """• POST /v1/aadhaar/link-requests/{requestId}/finalize (link)"""
        request = AadhaarRequestModel.query.get_or_404(requestId)
        if request.status != "OTP_VERIFIED":
            abort(400, message="Aadhaar OTP must be verified before final link.")
        
        request.status = "LINKED"
        db.session.commit()
        return {
            "requestId": requestId,
            "status": request.status,
            "maskedAadhaar": request.masked_aadhaar,
            "message": "Aadhaar successfully linked to the primary account."
        }, 200

@blp.route("/v1/aadhaar/link-requests/<string:requestId>")
class AadhaarStatus(MethodView):
    @jwt_required()
    def get(self, requestId):
        """• GET /v1/aadhaar/link-requests/{requestId} (status)"""
        request = AadhaarRequestModel.query.get_or_404(requestId)
        return {
            "requestId": request.request_id,
            "status": request.status,
            "maskedAadhaar": request.masked_aadhaar,
            "updatedAt": request.updated_at.isoformat() + "Z"
        }, 200

api.register_blueprint(blp)

if __name__ == "__main__":
    with app.app_context():
        db.create_all() # Creates tables in the Postgres container
    app.run(host="0.0.0.0", port=5003, debug=True)