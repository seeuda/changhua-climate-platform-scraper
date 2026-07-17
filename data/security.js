
// 資安相關
// #region 資安相關
/**
 * 安全性 實用工具
 */
var SecurityUtility = {
    /**
     * Html 編碼
     * @param {any} e - jQuery Element
     * @param {any} type - val, text, select, string (將 e 視為字串)
     * @returns
     */
    HtmlEncode: function (e, type) {
        if (!e || e.length == 0) {
            return "";
        }
        var ele = document.createElement('span');
        switch (type) {
            case "val":
                ele.appendChild(document.createTextNode(e.val()));
                break;
            case "text":
                ele.appendChild(document.createTextNode(e.text()));
                break;
            case "select":
                ele.appendChild(document.createTextNode(e.find("option:selected").val()));
                break;
            case "string":
                if (typeof (e) == "string") {
                    ele.appendChild(document.createTextNode(e));
                } else {
                    console.warn("type = string 時，傳入參數 [e] 必須為字串。");
                }
                break;
        }
        return this.HtmlDecode(ele.innerHTML);
    },
    /**
     * Html 解碼
     * @param {any} text 
     * @returns
     */
    HtmlDecode: function (text) {
        var temp = document.createElement("div");
        temp.innerHTML = text;
        var output = temp.innerText || temp.textContent;
        temp = null;
        return output;
    },
    /**
     * 取得 xss 轉譯後字串
     * @param {any} str
     */
    GetXssString: function (str) {
        if (!str) return "";
        return str.replace(/</g, '&lt;').replace(/>/g, '&gt;');
    },
    /**
     * 取得 xss 轉譯後字串
     * @param {any} str
     */
    GetXssStringDecode: function (str) {
        if (!str) return "";
        return str.replace(/&lt;/g, '<').replace(/&gt;/g, '>');
    },
    /**
     * 單引號 編碼
     * @param {any} str
     */
    QuotationMarkEncode: function (str) {
        if (!str) return "";
        return str.replace(/'/g, "&#39;");
    },
    /**
     * 單引號 解碼
     * @param {any} str
     */
    QuotationMarkDecode: function (str) {
        if (!str) return "";
        return str.replace(/&#39;/g, "'");
    }
};

// #endregion



