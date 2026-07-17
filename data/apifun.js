var refresh = true;
function NewsList(sqn, state) {
    refresh = state;
    var notFirstTime = true;
    var searchParams = new URLSearchParams(window.location.search);

    if (_Module == "ClimateGovernance") {
        //氣候資訊公開平臺
        if (searchParams.size != 0) {
            searchParams.forEach((value, key) => {
                searchParams.set(key, HtmlEncode(value));
            });
            SetClimateGovernanceList(searchParams);
        }
        else {
            return;
        }
    }

    Object.getOwnPropertyNames(QueryData).forEach((item) => {
        var t = $("#" + item);
        if (t != undefined && t.length > 0) {
            $(t).val(searchParams.get(item));
        }
    });
    var p = searchParams.get("p") ?? 1;
    var itemNum = CheckDisPlayCount(searchParams.get("dc"));
    $("#itemNum").val(itemNum);

    if (_Module == "Bilingual") {
        SearchBil(searchParams.get("q"))
    } else {
        SearchData(p, notFirstTime);
    }

}

function SetClimateGovernanceList(params) {
    var _startYear;
    var _endYear;
    if (isZh) {
        _startYear = 102;
        _endYear = 122;
    } else {
        _startYear = 2013;
        _endYear = 2033;
    }

    $("#q").val(params.get("q"));
    SetRadion("filter2Zone", params.get("cga"));
    switch (params.get("cga").toLowerCase()) {
        case "climategovernancecentral": $(".filterSubBtm").addClass("on");
            break;
        case "climategovernanceplace": $(".placeI").addClass("on");
            break;
    }
    var area = params.get("cgp");
    if (area != null) {
        $("#filter2Place21 > option").each(function () {
            if ($(this).val().toLowerCase() == area.toLowerCase()) {
                $(this).prop("selected", true);
            }
        });
        CityChange();
    }
    var city = params.get("cgac");
    if (city != null) {
        $("#filter2Place22 > option").each(function () {
            if ($(this).val().toLowerCase() == city.toLowerCase()) {
                $(this).prop("selected", true);
            }
        });
    }
    //GT
    var GT = params.get("gt");
    if (GT != null) {
        $("#filter2Type10, #filter2Type20").each(function () {
            if (GT == "all") {
                $(this).prop("checked", true);
            } else {
                if (GT.toLowerCase().indexOf($(this).val().toLowerCase()) > -1) {
                    $(this).prop("checked", true);
                } else {
                    $(this).prop("checked", false);
                    var name = $(this).attr("name");
                    $("input").filter(function () {
                        return $(this).attr("name") === name;
                    }).prop("checked", false);
                }
            }
        });
    }
    else {
        $("input[name='filter2Type1']").prop("checked", false);
        $("input[name='filter2Type2']").prop("checked", false);
    }
    //CGD 部門
    SetCheckBox("filter2Type1", params.get("cgd"));
    //CGF 類別
    SetCheckBox("filter2Type2", params.get("cgf"));

    //CGR
    SetCheckBox("filter2Report", params.get("cgr"));
    //CGS
    SetCheckBox("filter2Progress", params.get("cgs"));
    //CGYS

    $(".yearpicker1").yearpicker({
        startYear: _startYear,
        endYear: _endYear
    });

    $("#QryYearS").val(params.get("cgys"));
    $("#QryYearE").val(params.get("cgye"));
}
function SetRadion(name, val) {
    $("input[name='" + name + "']").each(function () {
        if ($(this).val().toLowerCase() == val.toLowerCase()) {
            $(this).prop("checked", "checked");
        }
    });
}
function SetCheckBox(name, strArray) {
    $("input[name='" + name + "']").each(function () {
        if (strArray == null) {
        } else if (strArray.toLowerCase() == "all") {
            $(this).prop("checked", true);
        } else {
            if (strArray.toLowerCase().indexOf($(this).val().toLowerCase()) > -1 || $(this).val().toLowerCase().indexOf(strArray.toLowerCase()) > -1) {
                $(this).prop("checked", true);
            } else {
                $(this).prop("checked", false);
            }
        }
    });
}

function SearchData(p, notFirstTime) {
    var displaycount = CheckDisPlayCount(null);
    var key = $("#sqn").val();
    if ($("#itemNum").length > 0) {
        displaycount = $("#itemNum").find(':selected').val();
    }
	var _herf = window.location.href.indexOf("energy");
	var q = _herf > -1 ? $("#QryKeyword").val() : $("#q").val();
	var start = _herf > -1 ? $("#QryDateS").val() : $("#start").val();
	var end = _herf > -1 ? $("#QryDateE").val() : $("#end").val();
    var obj = {
        key: key,
        lang: $(".webSitelanguage").attr("lang"),
        start: start,
		end: end,
		q: q,
        c4: $("#c4").val() ?? "",
        c5: $("#c5").val() ?? "",
        c6: $("#c6").val() ?? "",
        ct: $("#ct").val() ?? "",
        mc: $("#mc").val() ?? "",
        zc: $("#SysZipCode").val() ?? "",
        cf: $("#Chief").val() ?? "",
        bi: $("#Regulations").prop("checked") ?? "",
        cga: $("input[name='filter2Zone']:checked").val() ?? "",
        cgp: $("input[name='filter2Zone']:checked").val() == "ClimateGovernancePlace" ? $("#filter2Place21").val() ?? "" : "",
        cgac: $("input[name='filter2Zone']:checked").val() == "ClimateGovernancePlace" ? $("#filter2Place22").val() ?? "" : "",
        gt: $.map($('#filter2Type10:checked,#filter2Type20:checked'), function (n, i) { return n.value; }).join(','),
        cgd: $("#filter2Type10:checked").val() == "GT1" ? "all" : $.map($(':checkbox[name=filter2Type1]:checked'), function (n, i) { return n.value; }).join(','),
        cgf: $("#filter2Type20:checked").val() == "GT2" ? "all" : $.map($(':checkbox[name=filter2Type2]:checked'), function (n, i) { return n.value; }).join(','),
        cgr: $('#filter2Report0:visible:checked,#filter2Report4:visible:checked,#filter2Report7:visible:checked').val() == "all" ? "all" : $.map($(':checkbox[name=filter2Report]:checked'), function (n, i) { return n.value; }).join(','),
        cgs: $.map($(':checkbox[name=filter2Progress]:checked'), function (n, i) { return n.value; }).join(','),
        cgys: $("#QryYearS").val() ?? "",
        cgye: $("#QryYearE").val() ?? "",
        bilingualkeyword: $("#BilingualKeyword").val() ?? "",
        dc: displaycount,
        p: p
    };



    SearchObj(obj, notFirstTime);
}
var chk = false;
function SearchObj(obj, notFirstTime) {

    chk = false;
    //FECommon.basicLoadingOn();
    var msg = "";
    //檢核
    if ((obj.start != "" || obj.end != "") && obj.start != undefined && obj.end != undefined) {
        if (obj.start != "" && !dateIsValid(obj.start, obj.lang)) {
            msg += "起始時間格式有誤。\n The time format for StartDate is not allow. \n";
        }
        if (obj.end != "" && !dateIsValid(obj.end, obj.lang)) {
            msg += "結束時間格式有誤。\n The time format for EndDate is not allow. \n";
        }
        if (obj.start != "" && obj.end != "" && msg == "") {
            if (Date.parse(obj.start) > Date.parse(obj.end)) {
                msg += "結束時間請勿小於起始時間。\n EndDate should be later than StartDate. \n";
            }
        }
    }
    if ((obj.cgys != "" || obj.cgye != "") && obj.cgys != undefined && obj.cgye != undefined) {
        if (obj.cgys != "" && isNaN(parseInt(obj.cgys))) {
            msg += "起始公開年度格式有誤。\n The time format for StartYear is not allow. \n";
        }
        if (obj.cgye != "" && isNaN(parseInt(obj.cgye))) {
            msg += "結束公開年度格式有誤。\n The time format for EndYear is not allow. \n";
        }
        if (obj.cgys != "" && obj.cgye != "" && msg == "") {
            if (parseInt(obj.cgys) > parseInt(obj.cgye)) {
                msg += "結束公開年度請勿小於起始公開年度。\n EndYear should be later than StartYear. \n";
            }
        }
    }
    if (obj.txt != "" && obj.txt != undefined) {
        if (obj.txt.length > 50) {
            msg += "查詢字串請勿超過50個字。\n Keyword should not be longer than 50 letters. \n";
        }
    }
    if (msg != "") {
        alert(msg);
        //FECommon.basicLoadingOff();
        return;
    }
    SearchAjax(obj, notFirstTime);
}
function SearchAjax(obj, notFirstTime) {

    FECommon.basicLoadingOn();
    var innerHtml = "";
    var Url = GetApiUrl().concat("/WebAPI/WebsiteList/NewsList");
    var Regulations = obj.BI ? "1" : "0";

    var d = {};
    Object.getOwnPropertyNames(QueryData).forEach((item) => {
        Reflect.set(d, item, Reflect.get(obj, item));
    });

    Reflect.set(d, "Lang", $(".webSitelanguage").attr("lang"));
    Reflect.set(d, "MainSN", parseInt(obj.key));
    Reflect.set(d, "p", parseInt(obj.p));
    Reflect.set(d, "dc", parseInt(obj.dc));
    $.ajax({
        url: Url,
        method: 'POST',
        contentType: 'application/json',
        dataType: 'html',
        async: true,
        data: JSON.stringify(d),
        success: function (res) {
            innerHtml = HtmlEncode(res);
            $('.NewsList').empty();
            $('.NewsList').html(innerHtml).promise().done(function () {
                $('.datepicker1').datepicker();
                //FECommon.widgetMagnific();
                if ('URLSearchParams' in window) {
                    if (refresh) {
                        refresh = false;
                        return;
                    }
                    var searchParams = new URLSearchParams(window.location.search)
                    Object.getOwnPropertyNames(QueryData).forEach((item) => {
                        if (item != "Lang" || item != "MainSN") {
                            var t = Reflect.get(obj, item)
                            if (t != "" && t != undefined) { searchParams.set(item, t); } else { searchParams.delete(item); }
                        }
                        Reflect.set(d, item, Reflect.get(obj, item));
                    });
                    var hash = window.location.hash;
                    var newRelativePathQuery = window.location.pathname + '?' + searchParams.toString() + hash;
                    history.pushState(null, '', newRelativePathQuery);
                    switch (_Module) {
                        case "Bilingual":
                            $("html, body").animate({ scrollTop: $('#listNav').offset().top - $('.nav').height() }, 500);
                            break;
                        case "ClimateGovernance":
                            if (notFirstTime == undefined) {
                                $("html, body").animate({ scrollTop: $('.NewsList').offset().top - $('.nav').height() }, 500);
                            } else {
                                $('html').stop().animate({ scrollTop: 0 }, 100, 'linear');
                            }
                            break;
                        default:
                            $('html').stop().animate({ scrollTop: 0 }, 100, 'linear');
                            break;
                    }
                }
            });
        }, complete: function (data) {
            if ($("#start").length > 0) { SetDatepickNews("start"); }
            if ($("#end").length > 0) { SetDatepickNews("end"); }

            var IsAnykey = false;
            var missKey = ['key', 'displaycount', 'p'];
            $.each(Object.keys(obj), function (i, item) {
                if (missKey.filter(x => x == item).length == 0 && obj[item] != '') {
                    IsAnykey = true;
                    return;
                }
            });
            var openSearhList = ["Bilingual"];
            if (openSearhList.filter(x => x == _Module).length > 0) {
                IsAnykey = true;
            }
            if (IsAnykey) {
                $(".conSearchBarJs").removeClass("off");
            }

            //手風琴
            if (_ListType == "AccordionList") {
                if (tag == "" || tag == null) {
                    $(".qaI").each(function (i, item) {
                        if (i == 0) {
                            $(this).addClass("on now ");
                            $(this).find(".qaSwitch").attr("aria-expanded", "true");
                        }
                        return false;
                    });
                }
            }
            FEContent.mainQa();
            FEContent.mainCopyLink();
            if (FEContent?.mainMagnific instanceof Function) { FEContent.mainMagnific(); }
            if (FECommon?.mainMagnific instanceof Function) { FECommon.mainMagnific(); }
            FECommon.basicLoadingOff();
        }
    });
}


/*雙語NEW*/
function SearchBil(B) {
    if (B != null) {
        $("#q").val(B);
        $(".navI.on").removeClass("on");
        $(".navI").filter(function () {
            return $(this).data("id") === B;
        }).attr("class", "navI on");

        $("#filterBar3").removeClass("on").addClass("off");
        FEContent.mainFilter2Close($('.filterSwitch2Js'));
        $("#Bilingual").val("");
        $("#BilingualKeyword").val("")
    }
    SearchData(1);
}
/*雙語擴充查詢*/
function SearchBilingual() {
    $("#q").val($("#Bilingual").val());
    $(".navI.on").removeClass("on");

    SearchData(1);
}

/*左側選單*/
function LeftMenu(obj) {
    LeftMenuAjax(obj);
}
function LeftMenuAjax(obj) {
    if ($(".leftMenu").length > 0) {
        var innerHtml = "";
        var Url = GetApiUrl().concat("/WebAPI/WebsiteList/LeftMenu", "?key=" + obj);
        $.ajax({
            url: Url,
            method: 'POST',
            contentType: 'application/json',
            dataType: 'html',
            async: true,
            timeout: 3000,
            success: function (res) {
                innerHtml = HtmlEncode(res);
                $('.leftMenu').remove();
                $(".conWrap").prepend(innerHtml);
                FEContent.mainSidebar();
            }, error: function () {
            }
        });
    }
}

function PublicMeetingList() {
    FECommon.basicLoadingOn();
    var innerHtml = "";
    var cga = $("input[name='filter3Zone']:checked").val() ?? "";
    var Url = GetApiUrl().concat("/WebAPI/WebsiteList/PublicMeetingList", "?cga=" + cga);
    $.ajax({
        url: Url,
        method: 'POST',
        contentType: 'application/json',
        dataType: 'html',
        async: true,
        timeout: 3000,
        success: function (res) {
            innerHtml = HtmlEncode(res);
            $('.MeetingList').empty();
            $(".MeetingList").html(innerHtml).promise().done(function () {
                FECommon.basicLoadingOff();
            });

        }, complete: function () {
            FECommon.basicLoadingOff();
        }
    });
}

/*預設分頁*/
function CheckDisPlayCount(displaycount) {
    var intList = [15, 30, 45, 60];
    if (_NeedTwoDisplayCount.toUpperCase() == "TRUE") { intList = [30, 60, 90, 120]; }
    if (displaycount == null || displaycount == undefined) {
        var openSearhList = ["Bilingual"];
        if (openSearhList.filter(x => x == _Module).length > 0) {
            return displaycount = intList[2];
        }
        return displaycount = intList[0];

    } else {
        if (intList.filter(x => x == displaycount).length > 0) {
            return displaycount;
        } else {
            return intList[0];
        }
    }
}


function HtmlEncode(txt) {
    var ele = document.createElement('span');
    ele.appendChild(document.createTextNode(txt));
    return HtmlDecode(ele.innerHTML);
}
function HtmlDecode(text) {
    var temp = document.createElement("div");
    temp.innerHTML = text;
    var output = temp.innerText || temp.textContent;
    temp = null;
    return output;
}

function SetDatepickNews(id) {
    let d = new Date();
    let year = d.getFullYear();     // 西元年
    let month = d.getMonth() + 1;    // 月份 (0-11，需要+1)
    let day = d.getDate();         // 日期 (1-31)
    var nw = new Date(year, month, day);
    console.log(nw);
    $("#" + id).datepicker("option", {
        yearRange: "2023" + ":" + year,
        maxDate: d
    });
}