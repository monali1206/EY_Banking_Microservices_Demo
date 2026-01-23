import uuid, os
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
    "API_TITLE": "Linking PAN Service",
    "API_VERSION": "v1",
    "OPENAPI_VERSION": "3.0.3",
    "OPENAPI_URL_PREFIX": "/",
    "OPENAPI_SWAGGER_UI_PATH": "/swagger-ui",
    "OPENAPI_SWAGGER_UI_URL": "https://cdn.jsdelivr.net/npm/swagger-ui-dist/",
    # Database connection string for PostgreSQL
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
                    "bearerFormat": "JWT",
                    "description": "Enter: Bearer <your_token>"
                }
            }
        }
    }
})

# Initialize DB, API, and JWT
db = SQLAlchemy(app)
api = Api(app)
jwt = JWTManager(app)
blp = Blueprint("pan", "pan", description="RBI Compliant PAN Linking Lifecycle")

# --- DATABASE MODELS ---

class PanRequestModel(db.Model):
    __tablename__ = 'pan_link_requests'
    request_id = db.Column(db.String(50), primary_key=True)
    pan_number = db.Column(db.String(10), nullable=False)
    customer_name = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(30), default="PENDING_OTP")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# --- SCHEMAS ---
class PanStartSchema(Schema):
    panNumber = fields.Str(required=True, validate=validate.Regexp(r"^[A-Z]{5}[0-9]{4}[A-Z]$"))
    customerName = fields.Str(required=True)

class OtpVerifySchema(Schema):
    otp = fields.Str(required=True, validate=validate.Length(equal=6))

# --- ROUTES ---

@blp.route("/login")
class Login(MethodView):
    def post(self):
        """Get Token for Swagger Authorize"""
        return {"access_token": create_access_token(identity="admin")}

@blp.route("/v1/pan/link-requests")
class PanStart(MethodView):
    @jwt_required()
    @blp.arguments(PanStartSchema, location="form")
    def post(self, data):
        """• POST /v1/pan/link-requests (start)"""
        request_id = f"PAN_{uuid.uuid4().hex[:8].upper()}"
        new_request = PanRequestModel(
            request_id=request_id,
            pan_number=data['panNumber'],
            customer_name=data['customerName']
        )
        db.session.add(new_request)
        db.session.commit()
        return {
            "requestId": request_id,
            "status": new_request.status,
            "message": "Linking request initiated. Please send OTP."
        }, 201

@blp.route("/v1/pan/link-requests/<string:requestId>/send-otp")
class PanSendOtp(MethodView):
    @jwt_required()
    def post(self, requestId):
        """• POST /v1/pan/link-requests/{requestId}/send-otp"""
        request = PanRequestModel.query.get_or_404(requestId)
        request.status = "OTP_SENT"
        db.session.commit()
        return {
            "requestId": requestId,
            "status": request.status,
            "message": "OTP has been sent to registered mobile number"
        }, 200

@blp.route("/v1/pan/link-requests/<string:requestId>/verify-otp")
class PanVerifyOtp(MethodView):
    @jwt_required()
    @blp.arguments(OtpVerifySchema, location="form")
    def post(self, data, requestId):
        """• POST /v1/pan/link-requests/{requestId}/verify-otp"""
        request = PanRequestModel.query.get_or_404(requestId)
        # In production, logic would verify the 'data['otp']' here
        request.status = "OTP_VERIFIED"
        db.session.commit()
        return {
            "requestId": requestId,
            "status": request.status,
            "message": "OTP verified successfully"
        }, 200

@blp.route("/v1/pan/link-requests/<string:requestId>/finalize")
class PanFinalize(MethodView):
    @jwt_required()
    def post(self, requestId):
        """• POST /v1/pan/link-requests/{requestId}/finalize (link)"""
        request = PanRequestModel.query.get_or_404(requestId)
        if request.status != "OTP_VERIFIED":
            abort(400, message="OTP must be verified before finalizing link.")
        
        request.status = "LINKED"
        db.session.commit()
        return {
            "requestId": requestId,
            "status": request.status,
            "message": "PAN has been successfully linked to the account"
        }, 200

@blp.route("/v1/pan/link-requests/<string:requestId>")
class PanStatus(MethodView):
    @jwt_required()
    def get(self, requestId):
        """• GET /v1/pan/link-requests/{requestId} (status)"""
        request = PanRequestModel.query.get_or_404(requestId)
        return {
            "requestId": request.request_id,
            "status": request.status,
            "pan_number": f"******{request.pan_number[-4:]}", # Privacy masking
            "updatedAt": request.updated_at.isoformat() + "Z"
        }, 200

api.register_blueprint(blp)

if __name__ == "__main__":
    with app.app_context():
        db.create_all() # Automatically creates tables in Postgres
    app.run(host="0.0.0.0", port=5002, debug=True)