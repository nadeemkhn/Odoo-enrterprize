# Part of Odoo. See LICENSE file for full copyright and licensing details.
from odoo import http
from odoo.http import request

from ..utils.llm_api_service import LLMApiService


class AgentController(http.Controller):

    @http.route(["/ai/transcription/session"], methods=["POST"], type="jsonrpc", auth="user", readonly=True)
    def get_session_token(self, language: str, prompt: str):
        service = LLMApiService(request.env)

        session_params = {
            "input_audio_transcription": {
                "model": "gpt-4o-transcribe",
                "language": language,
                "prompt": prompt
            },
            "turn_detection": None,
            "input_audio_noise_reduction": {
                "type": "near_field"
            },
            "client_secret": {
                "expires_after": {
                    "anchor": "created_at",
                    "seconds": 7200
                },
            }
        }

        session = service.get_transcription_session(**session_params)
        return session
