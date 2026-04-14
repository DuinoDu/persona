# Copyright (c) 2022 Hongji Wang (jijijiang77@gmail.com)
#               2024 Shuai Wang (wsstriving@gmail.com)
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from importlib import import_module


def get_speaker_model(model_name: str):
    if model_name.startswith("XVEC"):
        module_name = "tdnn"
    elif model_name.startswith("ECAPA_TDNN"):
        module_name = "ecapa_tdnn"
    elif model_name.startswith("ResNet"):
        module_name = "resnet"
    elif model_name.startswith("REPVGG"):
        module_name = "repvgg"
    elif model_name.startswith("CAMPPlus"):
        module_name = "campplus"
    elif model_name.startswith("ERes2Net"):
        module_name = "eres2net"
    elif model_name.startswith("Res2Net"):
        module_name = "res2net"
    elif model_name.startswith("Gemini"):
        module_name = "gemini_dfresnet"
    elif model_name.startswith("whisper_PMFA"):
        module_name = "whisper_PMFA"
    elif model_name.startswith("ReDimNet"):
        module_name = "redimnet"
    elif model_name.startswith("SimAM_ResNet"):
        module_name = "samresnet"
    elif model_name.startswith("XI_VEC"):
        module_name = "xi_vector"
    elif model_name.startswith("W2VBert_Adapter_MFA"):
        module_name = "w2vbert_adapter_mfa"
    else:  # model_name error !!!
        print(model_name + " not found !!!")
        exit(1)
    module = import_module(f"speaker_id_tool.vendor_wespeaker.models.{module_name}")
    return getattr(module, model_name)
