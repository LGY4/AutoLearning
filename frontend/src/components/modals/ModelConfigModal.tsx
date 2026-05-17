import { useEffect, useState } from "react";
import { Button, Input, Modal, Select, Switch, Tag } from "antd";
import { apiGet } from "../../api/client";
import type { RuntimeStatus } from "../../types/baseline";

const MODEL_CONFIG_KEY = "autolearning_model_config";

interface ProviderPreset {
  label: string;
  api_base: string;
  model: string;
}

interface ModelConfig {
  provider: string;
  useCustom: boolean;
  apiBase: string;
  apiKey: string;
  modelName: string;
  temperature: number;
}

const DEFAULT_PRESETS: Record<string, ProviderPreset> = {
  deepseek: { label: "默认模型 (DeepSeek V4)", api_base: "https://api.deepseek.com/v1", model: "deepseek-chat" },
  moai: { label: "moai.top", api_base: "https://moai.top/v1", model: "gpt-5.4-mini" },
  spark: { label: "Spark X2", api_base: "", model: "spark-x" },
  ollama: { label: "Ollama (本地)", api_base: "http://localhost:11434/v1", model: "qwen2.5:7b" },
};

function loadConfig(): ModelConfig {
  try {
    const raw = localStorage.getItem(MODEL_CONFIG_KEY);
    if (raw) return JSON.parse(raw);
  } catch {}
  return { provider: "deepseek", useCustom: false, apiBase: "", apiKey: "", modelName: "", temperature: 0.4 };
}

function saveConfig(config: ModelConfig) {
  localStorage.setItem(MODEL_CONFIG_KEY, JSON.stringify(config));
}

export function getModelOverrides(): Record<string, string | number | null> | null {
  const config = loadConfig();
  if (!config.useCustom) return null;
  return {
    model_provider: config.provider === "spark" ? "spark" : "openai_compatible",
    model_api_base: config.apiBase || null,
    model_api_key: config.apiKey || null,
    model_name: config.modelName || null,
    model_temperature: config.temperature,
  };
}

interface Props {
  open: boolean;
  onClose: () => void;
}

export function ModelConfigModal({ open, onClose }: Props) {
  const [config, setConfig] = useState<ModelConfig>(loadConfig);
  const [runtime, setRuntime] = useState<RuntimeStatus | null>(null);
  const [presets, setPresets] = useState<Record<string, ProviderPreset>>(DEFAULT_PRESETS);

  useEffect(() => {
    if (open) {
      setConfig(loadConfig());
      apiGet<RuntimeStatus>("/system/runtime").then((r) => {
        setRuntime(r);
        if (r.model?.presets) setPresets(r.model.presets as Record<string, ProviderPreset>);
      }).catch(() => {});
    }
  }, [open]);

  const handleProviderChange = (provider: string) => {
    const preset = presets[provider];
    setConfig((c) => ({
      ...c,
      provider,
      apiBase: preset?.api_base ?? c.apiBase,
      modelName: preset?.model ?? c.modelName,
    }));
  };

  const handleSave = () => {
    saveConfig(config);
    onClose();
  };

  const providerOptions = Object.entries(presets).map(([key, p]) => ({
    value: key,
    label: p.label,
  }));

  return (
    <Modal title="模型配置" open={open} onCancel={onClose} onOk={handleSave} okButtonProps={{ htmlType: "button" }} keyboard={false} destroyOnClose width={520}>
      <div className="model-config-form">
        {runtime && (
          <div className="model-config-current">
            <span>系统默认</span>
            <Tag color="blue">{runtime.model.provider} / {runtime.model.model}</Tag>
          </div>
        )}

        <div className="model-config-row">
          <span>使用自定义模型</span>
          <Switch checked={config.useCustom} onChange={(v) => setConfig((c) => ({ ...c, useCustom: v }))} />
        </div>

        {config.useCustom && (
          <>
            <div className="model-config-field">
              <label>模型提供商</label>
              <Select
                value={config.provider}
                onChange={handleProviderChange}
                options={providerOptions}
                style={{ width: "100%" }}
              />
            </div>

            {config.provider !== "spark" && (
              <>
                <div className="model-config-field">
                  <label>API Base URL</label>
                  <Input
                    value={config.apiBase}
                    onChange={(e) => setConfig((c) => ({ ...c, apiBase: e.target.value }))}
                    placeholder="https://api.openai.com/v1"
                  />
                </div>
                <div className="model-config-field">
                  <label>API Key</label>
                  <Input.Password
                    value={config.apiKey}
                    onChange={(e) => setConfig((c) => ({ ...c, apiKey: e.target.value }))}
                    placeholder="sk-..."
                  />
                </div>
                <div className="model-config-field">
                  <label>模型名称</label>
                  <Input
                    value={config.modelName}
                    onChange={(e) => setConfig((c) => ({ ...c, modelName: e.target.value }))}
                    placeholder="gpt-5.4-mini"
                  />
                </div>
              </>
            )}

            {config.provider === "spark" && (
              <div className="model-config-hint">
                Spark X2 使用系统配置的 APPID/APIKey/APISecret，仅需选择模型。
                <div className="model-config-field" style={{ marginTop: 8 }}>
                  <label>Spark 模型</label>
                  <Select
                    value={config.modelName || "spark-x"}
                    onChange={(v) => setConfig((c) => ({ ...c, modelName: v }))}
                    options={[
                      { value: "spark-x", label: "Spark X2" },
                      { value: "spark", label: "Spark X1.5" },
                    ]}
                    style={{ width: "100%" }}
                  />
                </div>
              </div>
            )}

            <div className="model-config-field">
              <label>Temperature ({config.temperature})</label>
              <input
                type="range"
                min={0}
                max={2}
                step={0.1}
                value={config.temperature}
                onChange={(e) => setConfig((c) => ({ ...c, temperature: Number(e.target.value) }))}
                style={{ width: "100%" }}
              />
            </div>
          </>
        )}
      </div>
    </Modal>
  );
}
