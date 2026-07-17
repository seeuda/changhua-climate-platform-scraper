
$(function () {
    InitEditorContent();
    InitPlaceRow();
    InitPopup()
});

var globalWebSiteId = "";

$(document).on("click", "a", function (e) {
    var icount = $(this).find('i').length;
    if (icount > 0) {
        if ($(this).find('i')[icount - 1].innerHTML.toUpperCase().indexOf("PDF") >= 0) {
            window.open($(this)[icount -1].href);
            return false;
        }
    }
});

//**googleSearch*/

function gooSearch(lan, webSiteId, txt) {
    var _lan = lan == "zh-tw" ? "" : lan + "/";
    var _webSiteId = webSiteId == "CCA" ? "" : webSiteId + "/";
    var _txt = "";
    if (txt == undefined) {
        _txt = SecurityUtility.HtmlEncode($(".searchAreaIpt"), "val");
		 if (webSiteId.localeCompare("RAINGARDEN", undefined, { sensitivity: 'accent' }) === 0) {
			_txt = SecurityUtility.HtmlEncode($("[name=q]"), "val");
			}
    }
    else {
        _txt = txt;
    }
    location.href = "/".concat(_lan, _webSiteId, "search.html", "?q=", SecurityUtility.HtmlEncode(_txt, "string"));
    
}

//** change Header / Footer  */
function webSiteLange(lan, webSiteId) {
    globalWebSiteId = webSiteId;
    if (lan != null) {
        var lan = lan == "zh-tw" ? "" : "/" + lan;
        var webSiteId = webSiteId == "CCA" ? "" : "/" + webSiteId;
        if (!Array.from(document.styleSheets).some(sheet => sheet.href && sheet.href.includes("index.css")
        )) {
            $(".hd").load(lan + webSiteId + "/header.html", function () {
                FECommon.headerNavArwSet();
            });
            $(".ft").load(lan + webSiteId + "/footer.html", function () {
                UpdateDate();
                FECommon.footerFtNavDefault();
            });
        } else {
            UpdateDate();
        }
    }
}

//兩個引數，一個是cookie的名子，一個是值
function SetCookie(name, value) {
    var d = new Date();
    var strjson = JSON.stringify(value);
    d.setTime(d.getTime() + (1 * 2 * 60 * 60 * 1000)); //以1 hours 計算
    var expires = "expires=" + d.toGMTString();
    document.cookie = name + "=" + strjson + ";" + expires + ";cookie_flags: 'max-age=7200;secure;SameSite=lax;'";
}
function RemoveCookie(name) {
    var d = new Date();
    var strjson = JSON.stringify("");
    d.setTime(d.getTime() + (1 * 1 * 1 * 1 * -1)); //立刻過期
    var expires = "expires=" + d.toGMTString();
    document.cookie = name + "=" + strjson + ";" + expires + ";cookie_flags: 'max-age=7200;secure;SameSite=lax;'";

}
function dateIsValid(dateStr, lang) {
    var regex = /^\d{4}-\d{2}-\d{2}$/;
    if (lang == "zh-tw") {
        regex = /^\d{3}-\d{2}-\d{2}$/;
    }
    if (dateStr == undefined) {
        return true;
    }
    if (dateStr.match(regex) === null) {
        return false;
    }

    const date = new Date(dateStr);
    const timestamp = date.getTime();

    if (typeof timestamp !== 'number' || Number.isNaN(timestamp)) {
        return false;
    }

    return true;
}

function GoOpinion(sn) {
    var url = GetApiUrl().concat("/opinion/", sn);

    if (window.location.href.indexOf("/youth/") > 0) {
        url = GetApiUrl().concat("/youthopinion/privacypolicy");
    }

    window.open(url);
}
function GoCustomizedOpinion(path)
{

    var url = GetApiUrl().concat(path);

    var opinionclass = $('#EnergyOpinionClass').val();
    if (opinionclass !== undefined) {
        url = url.concat('/' + opinionclass);
    }

    window.open(url);
}

function GoFAQ(path) {
    var query = $('#FAQuery').val();
    if (query !== undefined)
    {
        var url = path.concat(query);
        window.location.replace(url);
    }
}

window.addEventListener('popstate', function (event) {
    window.location.reload();
});


var placeRowOriginalName = "";
/** 
 * 初始化 報告區塊資料、綁定事件
 */
function InitPlaceRow() {
    // When 'filter2Zone' is present, proceed with the following initialization bindings.
    if ($('input[type="radio"][name="filter2Zone"]').length > 0) {
        // Retain old field names
        placeRowOriginalName = $('.commonRow input[type="checkbox"]').attr('name');

        var currentZone = $('input[type="radio"][name="filter2Zone"]:checked').val();

        // Initial  load
        if (currentZone && currentZone.length > 0) {
            SwitchCommonRow(currentZone, 'default');
        }

        // onclick: The 'change' event has been used in the 'content.js', so here it is changed to the 'click' event.
        $('input[type="radio"][name="filter2Zone"]').off('click').on('click', function () {
            var subCurrentZone = $(this).val();
            SwitchCommonRow(subCurrentZone, 'zone');
        });
        $('.filterSubTop input[type="checkbox"]').off('click').on('click', function () {
            var subCurrentZone = $('input[type="radio"][name="filter2Zone"]:checked').val();
            SwitchCommonRow(subCurrentZone, 'subtop');
        });
        $('.filterSubBtm input[type="checkbox"]').off('click').on('click', function () {
            var subCurrentZone = $('input[type="radio"][name="filter2Zone"]:checked').val();
            SwitchCommonRow(subCurrentZone, 'subbtm');
        });
    }
}

/**
 * 切換報告
 * @param {any} currentZone 中央/地方 值
 * @param {any} type 類型判斷方式 default: 預設, zone: 中央/地方, subtop: 類型(父), subbtm: 類型(子)
 */
function SwitchCommonRow(currentZone, type) {
    var gt1Checked = $('input[id="filter2Type10"]').prop('checked');
    var gt2Checked = $('input[id="filter2Type20"]').prop('checked');
    var gt1ChildrenChecked = $('input[name="filter2Type1"]:checked').length > 0;
    var gt2ChildrenChecked = $('input[name="filter2Type2"]:checked').length > 0;

    // Default
    $('.commonRow').hide();
    $('.commonRowAll').find('input[type="checkbox"]').removeAttr('name');
    $('.commonRowPlace').find('input[type="checkbox"]').removeAttr('name');
    $('.commonRowGT2').find('input[type="checkbox"]').removeAttr('name');

    if (currentZone == 'ClimateGovernancePlace') {
        $('.commonRowPlace').show();
        $('.commonRowPlace').find('input[type="checkbox"]').attr('name', placeRowOriginalName);
    } else {
        if (type == 'zone') {
            $('.commonRowAll').show();
            $('.commonRowAll').find('input[type="checkbox"]').attr('name', placeRowOriginalName);
        } else if (type == 'subtop') {
            if (!gt1Checked && gt2Checked) {
                $('.commonRowGT2').show();
                $('.commonRowGT2').find('input[type="checkbox"]').attr('name', placeRowOriginalName);
            } else {
                $('.commonRowAll').show();
                $('.commonRowAll').find('input[type="checkbox"]').attr('name', placeRowOriginalName);
            }
        } else if (type == 'subbtm') {
            if (!gt1ChildrenChecked && gt2ChildrenChecked) {
                $('.commonRowGT2').show();
                $('.commonRowGT2').find('input[type="checkbox"]').attr('name', placeRowOriginalName);
            } else {
                $('.commonRowAll').show();
                $('.commonRowAll').find('input[type="checkbox"]').attr('name', placeRowOriginalName);
            }
        } else {
            if (!gt1Checked && !gt1ChildrenChecked && (gt2Checked || gt2ChildrenChecked)) {
                $('.commonRowGT2').show();
                $('.commonRowGT2').find('input[type="checkbox"]').attr('name', placeRowOriginalName);
            } else {
                $('.commonRowAll').show();
                $('.commonRowAll').find('input[type="checkbox"]').attr('name', placeRowOriginalName);
            }
        }
    }
}
function UpdateDate() {
    var now = new Date();
    var dateString = `${now.getFullYear() - 1911}-${(now.getMonth() + 1).toString().padStart(2, '0')}-${now.getDate().toString().padStart(2, '0')}`;
    var updateDateElement = document.querySelector('.updateDate');
    if (updateDateElement) {
        updateDateElement.innerHTML = updateDateElement.innerHTML.replace(/\$\{updateDate\}/, dateString);
    }
}
/**
 * 取得現在時間
 */
function GetNow() {
    // 現在時區
    const currentTimeZone = 8;
    var current = new Date();
    var now = new Date(current.getUTCFullYear(), current.getUTCMonth(), current.getUTCDate(), current.getUTCHours() + currentTimeZone, current.getUTCMinutes(), current.getUTCSeconds(), current.getUTCMilliseconds());
    return now;
}
/**
 * 取得當前語系
 * @returns
 */
function GetCurrentLang() {
    return SecurityUtility.HtmlEncode(GetElementAttribute($("html"), "lang"), "string");
}
/**
 * 初始化 編輯器內容
 */
function InitEditorContent() {
    // 判斷有無切換時間區塊
    $(".JQ_SwitchData").each(function () {
        var strStartDate = SecurityUtility.HtmlEncode(GetElementAttribute($(this), "data-startdate"), "string");
        var strEndDate = SecurityUtility.HtmlEncode(GetElementAttribute($(this), "data-enddate"), "string");

        var now = GetNow();
        if (strStartDate && strStartDate.length > 0) {
            var startDate = new Date(strStartDate);
            if (startDate != "Invalid Date" && now < startDate) {
                $(this).remove();
            }
        }
        if (strEndDate && strEndDate.length > 0) {
            var endDate = new Date(strEndDate);
            if (endDate != "Invalid Date" && now >= endDate) {
                $(this).remove();
            }
        }
    });

    // 判斷有無需要處理的符號
    Proofreading($("div"));


    function Proofreading(selector) {
        // 避免修改到原 html
        $(selector).contents().each(function () {
            if (this.nodeType === Node.TEXT_NODE && this.nodeValue.trim()) {
                // 修改純文字節點
                var content = this.nodeValue;

                content = AddSpace(content);

                content = ReplaceEnChars(content);

                // 更新內容
                this.nodeValue = content;
            } else if (this.nodeType === Node.ELEMENT_NODE) {
                // 子節點
                Proofreading(this);
            }
        });
    }

    /**
     * 增加英數前後空白
     * @param {any} content
     * @returns
     */
    function AddSpace(content) {
        content = LayoutUtility.Rule1(content);
        // 防止半形字符處於 match 交界的情況，再執行一次
        content = LayoutUtility.Rule1(content);

        content = LayoutUtility.Rule2(content);

        content = LayoutUtility.Rule3(content);

        content = LayoutUtility.Rule4(content);

        content = LayoutUtility.Rule5(content);

        content = LayoutUtility.Rule6(content);

        content = LayoutUtility.Rule7(content);

        content = LayoutUtility.Rule8(content);

        return content;
    }

    /**
     * 取代英文內文特定全形符號轉半形符號
     * @param {any} content
     * @returns
     */
    function ReplaceEnChars(content) {
        var lang = GetCurrentLang();
        // 英文語系才需取代
        if (lang.toLocaleLowerCase() == "en") {
            content = content
                .replace(/\’/g, "\'")
                .replace(/\‘/g, "\'")
                .replace(/\’/g, "\'")
                .replace(/\“/g, "\"")
                .replace(/\”/g, "\"")
                .replace(/\〝/g, "\"")
                .replace(/\〞/g, "\"");
        }
        return content;
    }
}
/**
 * 初始化 蓋板廣告
 */
function InitPopup() {
    if ($(".popup2Js").length > 0 && typeof (FECommon) == "object" && typeof (sessionStorage) == "object" && typeof (localStorage) == "object") {
        const webSiteId = typeof globalWebSiteId !== "undefined" ? globalWebSiteId : "default";
        const HEARTBEAT_KEY = `${webSiteId}_heartbeat`; // 心跳的 localStorage 鍵值
        const IS_AD_DISPLAY_KEY = `${webSiteId}_is_ad_display`; // 廣告顯示的鍵值
        const INTERVAL = 300; // 心跳更新間隔（毫秒）
        const LAST_HEARTBEAT_INTERVAL = 4000; // 前次心跳間隔（毫秒）

        // 判斷是否有上次的心跳時間?
        var lastHeartBeat = localStorage.getItem(HEARTBEAT_KEY);
        if (lastHeartBeat) {
            // 判斷上次心跳時間是否 > 前次心跳間隔 => 顯示蓋版廣告
            var dtLastHeartBeat = new Date(JSON.parse(lastHeartBeat));
            var now = GetNow();
            var diff = Math.abs(now - dtLastHeartBeat);
            var isAdDisplay = sessionStorage.getItem(IS_AD_DISPLAY_KEY);
                if (!isAdDisplay && diff > LAST_HEARTBEAT_INTERVAL) {
                FECommon.basicPopup2On();
                sessionStorage.setItem(IS_AD_DISPLAY_KEY, "true");
            }
        } else {
            FECommon.basicPopup2On();
            sessionStorage.setItem(IS_AD_DISPLAY_KEY, "true");
        }

        // 啟動心跳：每隔一段時間寫入心跳時間
        var intervalId = setInterval(function () {
            var heart = GetNow();
            localStorage.setItem(HEARTBEAT_KEY, JSON.stringify(heart));
        }, INTERVAL);

        // 當頁籤關閉時標記為廣告不再顯示
        window.addEventListener("beforeunload", () => {
            clearInterval(intervalId);
        });
    }
}

// element 屬性相關
// #region element 屬性相關
/**
 * 設定 element 屬性
 * @param {any} element - 元件
 * @param {any} attributeName - 屬性名稱
 * @param {any} value - 值
 * @returns
 */
function SetElementAttribute(element, attributeName, value) {
    return element.attr(attributeName, value);
}

/**
 * 取得 element 屬性
 * @param {any} element - 元件
 * @param {any} attributeName - 屬性名稱
 * @returns
 */
function GetElementAttribute(element, attributeName) {
    var attr = element.attr(attributeName);
    return attr ? attr : "";
}

/**
 * 移除 element 指定屬性
 * @param {any} element
 * @returns
 */
function RemoveElementAttributes(element, attributeName) {
    element.removeAttr(attributeName);
}

/**
 * 移除 element 所有屬性
 * @param {any} element
 * @returns
 */
function RemoveAllElementAttributes(element) {
    var attributes = $.map(element[0].attributes, function (item) {
        return item.name;
    });

    $.each(attributes, function (i, item) {
        element.removeAttr(item);
    });
}
// #endregion

// 版面相關
// #region 版面相關
/** 中文字符（含擴展區和兼容區） */
const chineseChars = /[\u4e00-\u9fa5\uF900-\uFAFF]/;
/** 半形字符（英文字母和數字） */
const halfWidthChars = /[A-Za-z0-9]/;
/** 半形符號 */
const punctuation = /[.,!?:;~\-\(\)\/#+]/;
/** Html TAG */
const htmlTag = /<[^>]+>/;
/** 空白字符 */
const spaceTag = /\s*/;

var LayoutUtility = {
    /**
    * 規則1: 半形字符前後是中文，前後都加空白
    * @param {any} content
    * @returns
    */
    Rule1: function (content) {
        // "網站APP啟用"、"民國77年"
        content = content.replace(
            new RegExp(`(${chineseChars.source})(${halfWidthChars.source}+)(${chineseChars.source})`, 'g'),
            '$1 $2 $3'
        );
        // "中山路-中正路路口"、" 材料680萬噸/年"
        content = content.replace(
            new RegExp(`(${chineseChars.source})(${punctuation.source}+)(${chineseChars.source})`, 'g'),
            '$1 $2 $3'
        );
        return content;
    },
    /**
    * 規則2: 半形字符前是中文，後是半形字符，僅前面加空白
    * @param {any} content
    * @returns
    */
    Rule2: function (content) {
        // "請聯絡12345678。"
        content = content.replace(
            new RegExp(`(${chineseChars.source})(${halfWidthChars.source}+)`, 'g'),
            '$1 $2'
        );
        // "請聯絡(02)1234-5678。"
        content = content.replace(
            new RegExp(`(${chineseChars.source})(${punctuation.source}+)`, 'g'),
            '$1 $2'
        );
        return content;
    },
    /**
    * 規則3: 半形字符後是中文，前是半形字符，僅後面加空白
    * @param {any} content
    * @returns
    */
    Rule3: function (content) {
        // "地址：100測試市"
        content = content.replace(
            new RegExp(`(${halfWidthChars.source}+)(${chineseChars.source})`, 'g'),
            '$1 $2'
        );
        // "文章「ABC內容」"
        content = content.replace(
            new RegExp(`(${punctuation.source}+)(${chineseChars.source})`, 'g'),
            '$1 $2'
        );
        return content;
    },
    /**
    * 規則4: 半形字符為英數連字，英數前後都加空白，符號前後也要加空白
    * @param {any} content
    * @returns
    */
    Rule4: function (content) {
        content = content.replace(
            new RegExp(`(${halfWidthChars.source}+)([-.]+)(?=${halfWidthChars.source}*)(${chineseChars.source})`, 'g'),
            ' $1 $2 $3'
        );
        return content;
    },
    /**
    * 規則5: 半形字符後是中文，前半段字符是英數，後半段字符是符號，則英數和符號前後加空白
    * @param {any} content
    * @returns
    */
    Rule5: function (content) {
        content = content.replace(
            new RegExp(`(${chineseChars.source})(${spaceTag.source})(${halfWidthChars.source}+)(${punctuation.source})(${spaceTag.source})(${chineseChars.source})`, 'g'),
            '$1$2$3 $4$5$6'
        );
        return content;
    },
    /**
    * 規則6: 半形字符前是中文，前半段字符是符號，後半段字符是英數，則英數和符號前後加空白
    * @param {any} content
    * @returns
    */
    Rule6: function (content) {
        content = content.replace(
            new RegExp(`(${chineseChars.source})(${spaceTag.source})(${punctuation.source})(${halfWidthChars.source}+)(${spaceTag.source})(${chineseChars.source})`, 'g'),
            '$1$2 $3 $4$5$6'
        );
        return content;
    },
    /**
    * 規則7: 處理純英數與中文混合
    * @param {any} content
    */
    Rule7: function (content) {
        content = content.replace(
            new RegExp(`(${chineseChars.source})(${halfWidthChars.source})`, 'g'),
            '$1 $2'
        );
        content = content.replace(
            new RegExp(`(${halfWidthChars.source})(${chineseChars.source})`, 'g'),
            '$1 $2'
        );
        return content;
    },
    /**
    * 規則8: 處理數字和符號（包含括弧）
    * @param {any} content
    */
    Rule8: function (content) {
        content = content.replace(
            new RegExp(`(${chineseChars.source})([0-9]+${punctuation.source}*)`, 'g'),
            '$1 $2'
        );
        content = content.replace(
            new RegExp(`([0-9]+${punctuation.source}*)(${chineseChars.source})`, 'g'),
            '$1 $2'
        );
        return content;
    }
};
// #endregion